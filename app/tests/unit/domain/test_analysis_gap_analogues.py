"""Аналоги прогалин в аналізі: що зберігається, чого сервер не пропускає, що означає «нема чесного аналога»."""

from typing import Any

import pytest

from domain.analysis.analysis import Gap, JobAnalysis
from domain.analysis.gap_analogues import Analogue, GapAnalogues
from domain.shared.errors import InvalidValue

GAPS = ["OpenTelemetry", "gRPC"]


def parse(**fields: Any) -> JobAnalysis:
    base: dict[str, Any] = {"score": 70, "summary": "A backend role.", "gaps": GAPS}
    return JobAnalysis.parse(**(base | fields))


def refusal(**fields: Any) -> str:
    with pytest.raises(InvalidValue) as error:
        parse(**fields)
    return error.value.message


def test_an_analysis_without_analogues_has_none_and_not_an_empty_list() -> None:
    assert parse().gap_analogues is None


def test_the_analogues_of_a_gap_keep_their_facts_and_explanation() -> None:
    analysis = parse(
        gap_analogues=[
            GapAnalogues(
                "OpenTelemetry",
                (
                    Analogue((4, 9), "Prometheus and Grafana dashboards"),
                    Analogue((12,), "ELK logging"),
                ),
            )
        ]
    )
    assert analysis.gap_analogues is not None
    assert analysis.gap_analogues[0] == GapAnalogues(
        "OpenTelemetry",
        (
            Analogue((4, 9), "Prometheus and Grafana dashboards"),
            Analogue((12,), "ELK logging"),
        ),
    )


def test_a_gap_without_an_entry_gets_no_honest_analogue_in_the_order_of_the_gaps() -> (
    None
):
    analysis = parse(
        gap_analogues=[GapAnalogues("gRPC", (Analogue((3,), "REST services"),))]
    )
    assert analysis.gap_analogues == (
        GapAnalogues("OpenTelemetry"),
        GapAnalogues("gRPC", (Analogue((3,), "REST services"),)),
    )
    assert analysis.gap_analogues[0].no_honest_analogue
    assert not analysis.gap_analogues[1].no_honest_analogue


def test_an_entry_without_analogues_means_no_honest_analogue() -> None:
    analysis = parse(gap_analogues=[GapAnalogues("gRPC", ())])
    assert analysis.gap_analogues == (
        GapAnalogues("OpenTelemetry"),
        GapAnalogues("gRPC"),
    )


def test_an_empty_list_says_every_gap_has_no_honest_analogue() -> None:
    assert parse(gap_analogues=[]).gap_analogues == (
        GapAnalogues("OpenTelemetry"),
        GapAnalogues("gRPC"),
    )


def test_an_empty_list_for_an_analysis_without_gaps_stays_empty() -> None:
    assert parse(gaps=[], gap_analogues=[]).gap_analogues == ()


def test_the_gap_of_an_entry_is_found_ignoring_case_and_spaces_and_stored_as_in_gaps() -> (
    None
):
    analysis = parse(
        gaps=[Gap("Open  Telemetry", "Have you used it?")],
        gap_analogues=[
            GapAnalogues(" open telemetry ", (Analogue((4,), "Prometheus"),))
        ],
    )
    assert analysis.gap_analogues == (
        GapAnalogues("Open Telemetry", (Analogue((4,), "Prometheus"),)),
    )


def test_repeated_fact_numbers_in_an_analogue_are_collapsed_in_order() -> None:
    analysis = parse(
        gap_analogues=[GapAnalogues("gRPC", (Analogue((5, 3, 5, 3, 8), "REST"),))]
    )
    assert analysis.gap_analogues is not None
    assert analysis.gap_analogues[1].analogues == (Analogue((5, 3, 8), "REST"),)


def test_the_explanation_is_collapsed_to_one_line() -> None:
    analysis = parse(
        gap_analogues=[GapAnalogues("gRPC", (Analogue((3,), "  REST\n  services "),))]
    )
    assert analysis.gap_analogues is not None
    assert analysis.gap_analogues[1].analogues[0].explanation == "REST services"


def test_two_entries_of_one_gap_are_merged() -> None:
    analysis = parse(
        gap_analogues=[
            GapAnalogues("gRPC", (Analogue((3,), "REST services"),)),
            GapAnalogues("GRPC", (Analogue((7,), "Protobuf contracts"),)),
        ]
    )
    assert analysis.gap_analogues is not None
    assert analysis.gap_analogues[1].analogues == (
        Analogue((3,), "REST services"),
        Analogue((7,), "Protobuf contracts"),
    )


def test_an_entry_for_a_gap_that_is_not_in_gaps_is_refused() -> None:
    assert refusal(gap_analogues=[GapAnalogues("Rust", (Analogue((3,), "C++"),))]) == (
        "gap_analogues: «Rust» — такої прогалини нема в gaps."
    )


def test_an_analogue_without_facts_is_refused() -> None:
    assert refusal(gap_analogues=[GapAnalogues("gRPC", (Analogue((), "REST"),))]) == (
        "gap_analogues: аналог прогалини «gRPC» без фактів."
    )


def test_an_analogue_without_an_explanation_is_refused() -> None:
    assert refusal(gap_analogues=[GapAnalogues("gRPC", (Analogue((3,), " "),))]) == (
        "gap_analogues: аналог прогалини «gRPC» без пояснення."
    )


def test_an_explanation_over_300_characters_is_refused() -> None:
    long = "x" * 301
    assert refusal(gap_analogues=[GapAnalogues("gRPC", (Analogue((3,), long),))]) == (
        "gap_analogues: пояснення аналога прогалини «gRPC» довше за 300 символів."
    )


def test_a_gap_may_have_five_analogues_but_not_six() -> None:
    five = tuple(Analogue((n,), f"Analogue {n}") for n in range(1, 6))
    assert parse(gap_analogues=[GapAnalogues("gRPC", five)]).gap_analogues is not None
    assert refusal(
        gap_analogues=[GapAnalogues("gRPC", (*five, Analogue((6,), "Analogue 6")))]
    ) == ("gap_analogues: прогалина «gRPC» — не більше 5 аналогів.")
