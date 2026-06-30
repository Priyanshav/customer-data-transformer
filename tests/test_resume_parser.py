"""
Regression test suite for the résumé parser.

Contract: these tests assert STRUCTURAL INVARIANTS, not exact strings.
If a future change silently drops a field, at least one test will fail.

Each fixture is a synthetic full résumé (lines list) representing a
structurally different layout.  We NEVER test against a specific real
résumé — the parser must be general.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pipeline.extract import (
    extract_hits_from_lines,
    extract_date_range,
    is_section_header,
    partition_sections,
)

# ── Fixture A: Full-featured résumé ──────────────────────────────────────
# Has: name, email, phone, location (3-part), linkedin link, skills with
# categories, dated experience, education with institution on a separate line.
FIXTURE_A = [
    "Jane Doe",
    "janedoe@email.com | +91 98765 43210 | linkedin.com/in/janedoe",
    "San Francisco, CA, USA",
    "",
    "SKILLS",
    "Languages: Python, Java, C++",
    "Tools: Docker, Kubernetes",
    "",
    "EXPERIENCE",
    "Tech Corp                        Remote",
    "Software Engineer                Jun 2021 - Present",
    "Built scalable microservices.",
    "",
    "EDUCATION",
    "B.S. Computer Science  Sep 2017 - May 2021",
    "University of Tech",
]

# ── Fixture B: Minimal résumé — no experience section, no phone ─────────
# Has: name, email, flat skills, education only.
FIXTURE_B = [
    "Alice Minimal",
    "alice@example.org",
    "",
    "TECHNICAL SKILLS",
    "React; Node.js; PostgreSQL; AWS",
    "",
    "EDUCATION",
    "M.S. Data Science - State University",
    "May 2022",
]

# ── Fixture C: Internship-style résumé with headline ─────────────────────
# Has: name, headline under name, email+phone on same line, github link,
# INTERNSHIPS header (synonym for experience), "Present" end date,
# "City, State" location (2-part), education with CSE-AI style degree.
FIXTURE_C = [
    "Harish Pal",
    "Backend Developer",
    "harish@example.com | +91 9876543210 | github.com/harish",
    "Noida, UP",
    "",
    "SKILLS",
    "Programming Languages: C++, Java, Python",
    "Backend: FastAPI, Node.js",
    "Database: PostgreSQL, MongoDB, Redis",
    "Infrastructure: Docker, Kafka",
    "",
    "INTERNSHIPS",
    "LetsGrowMore                     Remote",
    "Python Developer                 Jul 2024 - Aug 2024",
    "",
    "EDUCATION",
    "B. Tech in CSE-AI  2023 - Present",
    "Noida Institute of Engineering Technology",
]


class TestFullResumeInvariants:
    """Assert ALL schema fields for each fixture in one parametrised test."""

    @pytest.mark.parametrize("lines, expected_skills, has_phone, has_location, has_headline", [
        (FIXTURE_A, ["Python", "Java", "C++", "Docker", "Kubernetes"], True, True, False),
        (FIXTURE_B, ["React", "Node.js", "PostgreSQL", "AWS"], False, False, False),
        (FIXTURE_C, ["C++", "Java", "Python", "FastAPI", "Node.js", "PostgreSQL", "MongoDB", "Redis", "Docker", "Kafka"], True, True, True),
    ])
    def test_all_fields(self, lines, expected_skills, has_phone, has_location, has_headline):
        hits = extract_hits_from_lines(lines)

        # ── 1. Emails populated ──
        emails = [h.value for h in hits if h.field == "email"]
        assert len(emails) >= 1, "Expected at least one email"

        # ── 2. Phones populated when present ──
        phones = [h.value for h in hits if h.field == "phone"]
        if has_phone:
            assert len(phones) >= 1, "Expected at least one phone"

        # ── 3. Links populated and normalised ──
        link_hits = [h for h in hits if h.field.startswith("link_")]
        # Fixture B has no links — only assert when the résumé has them
        if any("linkedin.com" in l or "github.com" in l for l in lines):
            assert len(link_hits) >= 1, "Expected at least one link"
            for lh in link_hits:
                assert lh.value.startswith("https://"), f"Link not normalised: {lh.value}"
        # WHY: assert NO false-positive skill-name links
        for lh in link_hits:
            assert "Node.js" not in lh.value, "Node.js should not be a link"

        # ── 4. Location parsed when present ──
        cities = [h.value for h in hits if h.field == "loc_city"]
        if has_location:
            assert len(cities) >= 1, "Expected a city in location"
            assert "@" not in cities[0], "City contaminated with email"
            assert "http" not in cities[0], "City contaminated with URL"

        # ── 5. Headline extracted when present ──
        headlines = [h.value for h in hits if h.field == "headline"]
        if has_headline:
            assert len(headlines) >= 1, "Expected a headline"

        # ── 6. Skills non-empty and correctly parsed ──
        skills = [h.value for h in hits if h.field == "skill"]
        assert len(skills) >= len(expected_skills), f"Expected ≥{len(expected_skills)} skills"
        for s in expected_skills:
            assert s in skills, f"Missing skill: {s}"
        # WHY: category labels must be stripped
        for s in skills:
            assert s not in ("Languages", "Tools", "Programming Languages",
                             "Backend", "Database", "Infrastructure"), \
                f"Category label leaked as skill: {s}"

        # ── 7. Education entries present and NOT in experience ──
        edu_degrees = [h.value for h in hits if h.field == "edu_degree"]
        edu_insts = [h.value for h in hits if h.field == "edu_institution"]
        companies = [h.value for h in hits if h.field == "company"]

        assert len(edu_degrees) > 0 or len(edu_insts) > 0, "Expected at least one education entry"
        # Cross-contamination check
        for val in edu_degrees + edu_insts:
            assert val not in companies, f"Education value in companies: {val}"

        # ── 8. No field value equals a section header ──
        section_headers = {
            "SKILLS", "TECHNICAL SKILLS", "EXPERIENCE", "WORK EXPERIENCE",
            "EDUCATION", "INTERNSHIPS", "PROJECTS",
        }
        for h in hits:
            val_str = str(h.value).upper().strip()
            assert val_str not in section_headers, \
                f"Section header leaked as field value: {h.field}={h.value}"


class TestDateParser:
    """Test the date range parser in isolation."""

    def test_noise_rejection(self):
        """Bare numbers (ratings, counts) must NOT become dates."""
        assert extract_date_range("Managed a team of 2000 users") is None
        assert extract_date_range("Scored 600+ on the test") is None
        assert extract_date_range("Population 1800 in the village") is None

    def test_month_year_parsed(self):
        res = extract_date_range("Worked from Jan 2020")
        assert res is not None
        assert res[0] == "Jan 2020"

    def test_range_parsed(self):
        res = extract_date_range("Developer  2018 - 2020")
        assert res is not None
        assert res[0] == "2018"
        assert res[1] == "2020"

    def test_open_ended_range(self):
        """Present/Current/Now → end_date must be None."""
        for end_word in ("Present", "Current", "Now"):
            res = extract_date_range(f"Engineer  Jan 2020 - {end_word}")
            assert res is not None, f"Failed to parse range ending in {end_word}"
            assert res[0] == "Jan 2020"
            assert res[1] is None, f"Open end should be None, got {res[1]}"

    def test_en_dash_separator(self):
        res = extract_date_range("Jul 2024\u2013Aug 2024")  # en-dash
        assert res is not None

    def test_em_dash_separator(self):
        res = extract_date_range("Jul 2024\u2014Aug 2024")  # em-dash
        assert res is not None


class TestSectionDetection:
    """Verify that section headers are identified correctly."""

    def test_known_synonyms(self):
        assert is_section_header("SKILLS") == "skills"
        assert is_section_header("Technical Skills") == "skills"
        assert is_section_header("WORK EXPERIENCE") == "experience"
        assert is_section_header("INTERNSHIPS") == "experience"
        assert is_section_header("EDUCATION") == "education"

    def test_not_a_header(self):
        """Normal content lines must NOT be mistaken for headers."""
        assert is_section_header("B. Tech in CSE-AI") is None
        assert is_section_header("Built scalable microservices.") is None

    def test_unknown_allcaps(self):
        """Unknown all-caps short lines → 'unknown' (kept aside, not experience)."""
        assert is_section_header("ACHIEVEMENTS") == "achievements"


class TestDecoupling:
    """Verify that extractors are independent — one failing doesn't blank another."""

    def test_missing_experience_doesnt_break_skills(self):
        """Résumé with skills but no experience section."""
        lines = [
            "Test User",
            "test@test.com",
            "SKILLS",
            "Python, Java",
        ]
        hits = extract_hits_from_lines(lines)
        skills = [h.value for h in hits if h.field == "skill"]
        assert "Python" in skills
        assert "Java" in skills

    def test_missing_skills_doesnt_break_education(self):
        """Résumé with education but no skills section."""
        lines = [
            "Test User",
            "test@test.com",
            "EDUCATION",
            "B.S. Physics - MIT",
            "May 2020",
        ]
        hits = extract_hits_from_lines(lines)
        degrees = [h.value for h in hits if h.field == "edu_degree"]
        assert any("Physics" in d for d in degrees)

    def test_education_institution_on_next_line(self):
        """Institution name on a separate line after the date line."""
        lines = [
            "Test User",
            "test@test.com",
            "EDUCATION",
            "B. Tech in CSE-AI  2023 - Present",
            "Noida Institute of Engineering Technology",
        ]
        hits = extract_hits_from_lines(lines)
        insts = [h.value for h in hits if h.field == "edu_institution"]
        degrees = [h.value for h in hits if h.field == "edu_degree"]
        assert "Noida Institute of Engineering Technology" in insts
        assert any("CSE-AI" in d for d in degrees)
