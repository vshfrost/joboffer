import { createContext, use, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import type { Contacts, FieldErrors, Profile, ProfileSection } from "../../domain/profile";
import { SECTION_ORDER } from "../../domain/profile";
import {
  formToLocations,
  formToRules,
  formToTarget,
  locationsToForm,
  rulesToForm,
  targetToForm,
  type FormParse,
  type LocationsForm,
  type RulesForm,
  type TargetForm,
} from "../../domain/profileForms";
import { useProfileServices } from "./ProfileServices";

/** Форми редагованих розділів. */
export interface FormsMap {
  target: TargetForm;
  locations: LocationsForm;
  rules: RulesForm;
  contacts: Contacts;
}
export type EditableSection = keyof FormsMap;

interface Codec<S extends EditableSection> {
  toForm(profile: Profile): FormsMap[S];
  toValue(form: FormsMap[S]): FormParse<Profile[S]>;
}

const CODECS: { [S in EditableSection]: Codec<S> } = {
  target: { toForm: (profile) => targetToForm(profile.target), toValue: formToTarget },
  locations: {
    toForm: (profile) => locationsToForm(profile.locations),
    toValue: (form) => ({ ok: true, value: formToLocations(form) }),
  },
  rules: { toForm: (profile) => rulesToForm(profile.rules), toValue: (form) => ({ ok: true, value: formToRules(form) }) },
  contacts: { toForm: (profile) => ({ ...profile.contacts }), toValue: (form) => ({ ok: true, value: form }) },
};

export const SAVE_FAILED = "Не вдалося зберегти. Введене не втрачено — спробуй ще раз.";
export const FIELDS_INVALID = "Перевір поля з помилками.";

interface Runtime {
  saving: boolean;
  /** Сервер підтвердив збереження, і після цього форму не чіпали. */
  saved: boolean;
  general: string | null;
  fieldErrors: FieldErrors;
  /** Росте з кожною відхиленою спробою: редактор переносить фокус на перше поле з помилкою. */
  errorToken: number;
}

const IDLE: Runtime = { saving: false, saved: false, general: null, fieldErrors: {}, errorToken: 0 };

export interface SectionApi<S extends EditableSection> {
  form: FormsMap[S];
  dirty: boolean;
  saving: boolean;
  saved: boolean;
  general: string | null;
  fieldErrors: FieldErrors;
  errorToken: number;
  /** `clears` — поля сервера, помилки яких зникають, бо поле змінено. */
  change(patch: Partial<FormsMap[S]>, clears?: readonly string[]): void;
  cancel(): void;
  save(): Promise<void>;
}

export interface ProfileState {
  saved: Profile;
  /** Розділи з незбереженими змінами в порядку меню. */
  dirtySections: ProfileSection[];
  section<S extends EditableSection>(section: S): SectionApi<S>;
}

type Load = { status: "loading" } | { status: "error" } | { status: "ready"; profile: Profile };

interface ProfileContextValue {
  load: Load;
  reload(): void;
  state: ProfileState | null;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

const same = (first: unknown, second: unknown): boolean => JSON.stringify(first) === JSON.stringify(second);

/**
 * Профіль, завантажений на час візиту на сторінку, і чернетки розділів у памʼяті: вони переживають
 * переходи між розділами, але не перезавантаження сторінки (персональні дані не йдуть у сховище браузера).
 */
export function ProfileProvider({ children }: { children: ReactNode }) {
  const services = useProfileServices();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [drafts, setDrafts] = useState<Partial<FormsMap>>({});
  const [runtimes, setRuntimes] = useState<Partial<Record<EditableSection, Runtime>>>({});

  useEffect(() => {
    let cancelled = false;
    void services.load().then((outcome) => {
      if (!cancelled) {
        setLoad(outcome.ok ? { status: "ready", profile: outcome.profile } : { status: "error" });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, attempt]);

  const reload = useCallback(() => {
    setLoad({ status: "loading" });
    setAttempt((current) => current + 1);
  }, []);

  const profile = load.status === "ready" ? load.profile : null;

  const state = useMemo<ProfileState | null>(() => {
    if (profile === null) {
      return null;
    }
    const runtimeOf = (section: EditableSection): Runtime => runtimes[section] ?? IDLE;
    const patchRuntime = (section: EditableSection, patch: Partial<Runtime>) =>
      setRuntimes((current) => ({ ...current, [section]: { ...(current[section] ?? IDLE), ...patch } }));
    const dropDraft = (section: EditableSection) =>
      setDrafts((current) => {
        const rest = { ...current };
        delete rest[section];
        return rest;
      });

    function section<S extends EditableSection>(name: S): SectionApi<S> {
      const codec = CODECS[name] as Codec<S>;
      const baseline = codec.toForm(profile as Profile);
      const draft = drafts[name] as FormsMap[S] | undefined;
      const form = draft ?? baseline;
      const runtime = runtimeOf(name);
      return {
        form,
        dirty: draft !== undefined,
        saving: runtime.saving,
        saved: runtime.saved,
        general: runtime.general,
        fieldErrors: runtime.fieldErrors,
        errorToken: runtime.errorToken,
        change(patch, clears = []) {
          const next = { ...form, ...patch };
          if (same(next, baseline)) {
            dropDraft(name);
          } else {
            setDrafts((current) => ({ ...current, [name]: next }));
          }
          const remaining = Object.fromEntries(Object.entries(runtime.fieldErrors).filter(([field]) => !clears.includes(field)));
          patchRuntime(name, { saved: false, general: null, fieldErrors: remaining });
        },
        cancel() {
          dropDraft(name);
          patchRuntime(name, { saved: false, general: null, fieldErrors: {} });
        },
        async save() {
          const parsed = codec.toValue(form);
          if (!parsed.ok) {
            patchRuntime(name, { saved: false, general: null, fieldErrors: parsed.errors, errorToken: runtime.errorToken + 1 });
            return;
          }
          patchRuntime(name, { saving: true, saved: false, general: null, fieldErrors: {} });
          const outcome = await services.save(name, parsed.value);
          if (outcome.ok) {
            setLoad({ status: "ready", profile: outcome.profile });
            dropDraft(name);
            patchRuntime(name, { saving: false, saved: true });
          } else if (outcome.kind === "invalid") {
            patchRuntime(name, { saving: false, fieldErrors: outcome.fieldErrors, errorToken: runtime.errorToken + 1 });
          } else {
            patchRuntime(name, { saving: false, general: SAVE_FAILED });
          }
        },
      };
    }

    return {
      saved: profile,
      dirtySections: SECTION_ORDER.filter((name) => name in drafts),
      section,
    };
  }, [profile, drafts, runtimes, services]);

  const value = useMemo(() => ({ load, reload, state }), [load, reload, state]);
  return <ProfileContext value={value}>{children}</ProfileContext>;
}

export function useProfileLoad(): ProfileContextValue {
  const value = use(ProfileContext);
  if (value === null) {
    throw new Error("useProfileLoad потребує ProfileProvider");
  }
  return value;
}

/** Профіль і чернетки; викликати лише під екраном, який показується після завантаження. */
export function useProfile(): ProfileState {
  const { state } = useProfileLoad();
  if (state === null) {
    throw new Error("Профіль ще не завантажено");
  }
  return state;
}
