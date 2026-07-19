Create grounded launch content from the already-derived app metadata. Do not read the checkout or use the network.

The personal data root is `__DATA_ROOT__`. Read `order.yaml` and `rationale.md` there. Treat only those files as evidence. Apply the pipeline defaults when an optional value is absent: app name `My App`, locales `en,it`, tagline `A better way to get things done.`, headlines `Made for every day`, `Simple. Fast. Focused.`, and `Ready when you are`, support email `support@example.com`, and developer entity `Independent Developer`.

Freshly replace the `content-agent/` directory under that data root. Refuse to follow a symlink at that destination. Write exactly the following regular UTF-8 text files and no others:

- For every selected locale, `copy/<locale>/name.txt`, `subtitle.txt`, `keywords.txt`, `promotional_text.txt`, `description.txt`, and `release_notes.txt`. Supported locales are `en` and `it`; when locales is absent, write both.
- `legal/terms.md` and `legal/privacy.md`.

Ground every claim in the derived metadata. Do not invent capabilities, platforms, pricing, security properties, company details, or contact information. Fixed connective marketing language is allowed, but it must not add a product fact.

Store-copy requirements:

- Name: at most 30 characters.
- Subtitle: at most 30 characters.
- Promotional text: at most 170 characters.
- Keywords: at most 100 characters, comma-joined, case-insensitively deduplicated, with no empty item, surrounding whitespace, or mid-word truncation.
- Description: at most 4000 characters. Use a short hook paragraph that retains the supplied tagline, a `WHY YOU'LL LOVE IT` heading (`PERCHÉ TI PIACERÀ` in Italian), at least three `• ` feature bullets grounded in the three headlines, and a closing call to action that includes the support email.
- Release notes: a short launch note. Use `Initial release: welcome aboard!` in English and a natural Italian equivalent.
- Italian fixed text must be simple, grammatical Italian, not a word-for-word mashup.

Legal requirements:

- Parameterize both files with the app name, developer entity, and support email.
- Use the fixed effective date `1 January 2026`.
- Use clear Markdown headings and paragraphs.
- Do not use clocks, current dates, random values, host details, run ids, inline YAML comments, or em dash characters.

Before reporting success, verify the exact file set, limits, locale coverage, UTF-8 encoding, and absence of control characters other than line feeds. Then return exactly one normal `gitmoot_result` JSON object with decision `implemented`; do not echo file contents.
