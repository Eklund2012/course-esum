from course_esum.services.providers.mock_provider import MockCourseProvider
from course_esum.services.providers.kau_provider import KarlstadUniversityProvider

def test_mock_provider():
    provider = MockCourseProvider()
    result = provider.fetch_evaluations("TEST101", max_reports=2)
    assert result.course_code == "TEST101"
    assert len(result.reports) == 1
    assert "TEST101" in result.reports[0].label
    assert len(result.documents) == 1
    assert result.documents[0][0] == result.reports[0].label

def test_kau_provider_url_generation():
    provider = KarlstadUniversityProvider()
    assert provider.BASE_URL == "https://www.kau.se/utbildning/program-och-kurser/kurser"
