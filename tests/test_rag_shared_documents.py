from types import SimpleNamespace

import pytest

from src.rag_vector import VectorRAG, _document_sharing_metadata
from tests.helpers.embedding_lanes import FakeCollection, FakeEmbedder


@pytest.mark.parametrize('owner', ['matas', 'ugne', 'future_user'])
def test_search_includes_shared_courses_without_other_users_private_documents(owner):
    collection = FakeCollection('shared-test')
    collection.add(
        ids=['course', 'matas-private', 'ugne-private', 'ownerless'],
        embeddings=[[1.0]] * 4,
        documents=['panic course', 'panic private matas', 'panic private ugne', 'panic ownerless'],
        metadatas=[{'owner': 'matas', 'visibility': 'shared'}, {'owner': 'matas'}, {'owner': 'ugne'}, {}],
    )
    rag = VectorRAG.__new__(VectorRAG)
    rag._healthy = True
    rag._lanes = [SimpleNamespace(name='fastembed', collection=collection, client=FakeEmbedder(1, 'test', ''), count=collection.count, encode=lambda texts: [[1.0] for _ in texts])]
    expected = {'course'}
    if owner in {'matas', 'ugne'}:
        expected.add(owner + '-private')
    assert {hit['id'] for hit in rag.search('panic', k=10, owner=owner)} == expected
    assert {hit['id'] for hit in rag._keyword_search_fallback('panic', k=10, owner=owner)} == expected


def test_only_configured_directory_is_shared_including_reindexing(monkeypatch, tmp_path):
    from src import settings

    root = tmp_path / 'moodle'
    root.mkdir()
    outside = tmp_path / 'private.pdf'
    link = root / 'outside.pdf'
    link.symlink_to(outside)
    monkeypatch.setattr(settings, 'get_setting', lambda *args: [str(root)])
    assert _document_sharing_metadata({'source': str(root / 'course.pdf')})['visibility'] == 'shared'
    assert 'visibility' not in _document_sharing_metadata({'source': str(tmp_path / 'moodle-private/course.pdf')})
    assert 'visibility' not in _document_sharing_metadata({'source': str(link)})
    assert 'visibility' not in _document_sharing_metadata({'source': 'relative/course.pdf'})
