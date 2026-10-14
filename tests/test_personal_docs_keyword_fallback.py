"""Cataloged folders skip extraction at startup but still answer keyword fallback."""

from src.personal_docs import catalog_personal_files, retrieve_personal_keyword


def test_cataloged_files_are_read_on_first_keyword_search(tmp_path):
    (tmp_path / "lecture.md").write_text("Operant conditioning uses reinforcement schedules.", encoding="utf-8")

    index = catalog_personal_files(str(tmp_path))
    assert index[0]["chunks"] == []

    results = retrieve_personal_keyword(index, "reinforcement schedules", k=3)

    assert len(results) == 1 and "lecture.md" in results[0]
    assert index[0]["chunks"] and "_chunks_pending" not in index[0]
