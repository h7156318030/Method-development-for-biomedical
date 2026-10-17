## What this changes

<!-- One or two sentences. Why, not only what. -->

## Requirement and tests

- URS row(s) in `docs/URS_需求与测试追溯.md`:
- New or updated tests (`test_URS<n>_...`):

## Checklist

- [ ] `python -X utf8 -m unittest discover -s tests` passes locally
- [ ] Documentation updated where behaviour changed (README / README_en / URS / CHANGELOG)
- [ ] New UI strings added to `app/static/i18n_extra_en.js` (`python tools/i18n_missing.py` checks)
- [ ] No credentials, personal data, or real project / method / document content in the diff or in test fixtures
- [ ] Audit trail, e-signature and separation-of-duties rules are unchanged, or the description explains the change and why
