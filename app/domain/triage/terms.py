"""Словник технологій і доменних термінів бекенд-фінтех вакансій: канонічна назва й синоніми."""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Term:
    """Канонічний термін. `synonyms` шукаються без регістру цілим словом (після `fold`);
    `literals` — точно як написано, з урахуванням регістру й символів («Go», «C++»):
    так «Go» не плутається зі словом «go» у звичайному тексті."""

    name: str
    synonyms: tuple[str, ...] = ()
    literals: tuple[str, ...] = ()


def literal_pattern(literal: str) -> re.Pattern[str]:
    """Літерал як окреме слово: без літер, цифр і дефіса навколо («Google», «Go-to-market» — ні)."""
    return re.compile(rf"(?<![\w-]){re.escape(literal)}(?![\w+#-])")


TERMS: tuple[Term, ...] = (
    Term("Python", ("python",)),
    Term("Java", ("java",)),
    Term("Kotlin", ("kotlin",)),
    Term("Go", ("golang",), ("Go",)),
    Term("Rust", ("rust",)),
    Term("Scala", ("scala",)),
    Term("Elixir", ("elixir",)),
    Term("PHP", ("php",)),
    Term("Ruby", ("ruby",)),
    Term("C#", (), ("C#",)),
    Term("C++", (), ("C++",)),
    Term(".NET", ("dotnet",), (".NET",)),
    Term("JavaScript", ("javascript", "js")),
    Term("TypeScript", ("typescript",)),
    Term("Node.js", ("nodejs", "node js")),
    Term("React", ("react", "reactjs", "react js")),
    Term("Vue", ("vue", "vuejs", "vue js")),
    Term("Angular", ("angular",)),
    Term("Django", ("django",)),
    Term("FastAPI", ("fastapi",)),
    Term("Flask", ("flask",)),
    Term("Spring", ("spring boot", "spring framework")),
    Term("SQLAlchemy", ("sqlalchemy",)),
    Term("Celery", ("celery",)),
    Term("PostgreSQL", ("postgresql", "postgres")),
    Term("MySQL", ("mysql",)),
    Term("MongoDB", ("mongodb", "mongo")),
    Term("Redis", ("redis",)),
    Term("Elasticsearch", ("elasticsearch", "elastic search")),
    Term("SQL", ("sql",)),
    Term("NoSQL", ("nosql",)),
    Term("Kafka", ("kafka",)),
    Term("RabbitMQ", ("rabbitmq", "rabbit mq")),
    Term("Airflow", ("airflow",)),
    Term("Docker", ("docker",)),
    Term("Kubernetes", ("kubernetes", "k8s")),
    Term("Terraform", ("terraform",)),
    Term("AWS", ("aws", "amazon web services")),
    Term("GCP", ("gcp", "google cloud", "google cloud platform")),
    Term("Azure", ("azure",)),
    Term("CI/CD", ("ci cd", "cicd")),
    Term("Git", ("git",)),
    Term("Linux", ("linux",)),
    Term("Prometheus", ("prometheus",)),
    Term("Grafana", ("grafana",)),
    Term("REST", ("rest api", "rest apis", "restful")),
    Term("GraphQL", ("graphql",)),
    Term("gRPC", ("grpc",)),
    Term("Microservices", ("microservices", "microservice", "micro services")),
    Term("TDD", ("tdd", "test driven development")),
    Term("DDD", ("ddd", "domain driven design")),
    Term("PSD2", ("psd2",)),
    Term("SEPA", ("sepa",)),
    Term("ISO 20022", ("iso 20022",)),
    Term("KYC", ("kyc",)),
    Term("AML", ("aml",)),
    Term("PCI DSS", ("pci dss", "pci")),
    Term("Open Banking", ("open banking",)),
    Term("Stripe", ("stripe",)),
    Term("Adyen", ("adyen",)),
)
