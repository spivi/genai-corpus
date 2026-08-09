# Fixture corpus

Synthetic, non-media stand-ins used only to exercise `genai_corpus.corpus` in tests,
the notebook smoke test, and CI (`SPZ-43`). This is **not** a sample of the real
corpus — it is small on purpose (well under the 5 MB budget CI asserts) and every
asset is a plain-text document, so nothing here trips the media-by-extension ignore
rules in `.gitignore`.

The real corpus (`SPZ-45`) is generated separately, capped at 5 GB, frozen as `v1.0`
with its own checksum manifest, and published as a Hugging Face dataset. It is never
committed to this or any series repo.
