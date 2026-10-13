# Meadow Pointe II CDD Public Records Search

Independent resident-maintained public full-text search of publicly linked CDD PDFs. Not affiliated with the CDD.

## Quick setup

1. Extract this ZIP on your computer. Upload its **contents** to the root of your existing `clazar25/meadow-pointe-ii-records` GitHub repository, preserving `docs/`, `scripts/`, and `.github/workflows/`. Do not upload the ZIP alone. Replace the existing README if asked.
2. In the repository, open **Actions** > **Update public CDD search index** > **Run workflow**. Enable Actions if prompted.
3. In **Settings** > **Actions** > **General**, ensure workflow permissions allow **Read and write permissions** if the indexing commit fails with HTTP 403. Save.
4. After the indexing run succeeds, go to **Settings** > **Pages**. Choose **Deploy from a branch**, branch **main**, folder **/docs**, then Save.
5. Your public site should be `https://clazar25.github.io/meadow-pointe-ii-records/` after publishing.

The scheduled collector checks weekly on Mondays. It follows public document/meeting pages, downloads linked PDFs temporarily, extracts searchable text per page, and writes `docs/records.json`. PDFs remain on the official website and search results link there. Previously indexed text is retained if a document link disappears. No AI-generated decision claims are made.

## Important limitations

- This is a **starter implementation**. The official site's HTML and PDF links have not yet been validated against a successful live indexing run. Check Actions logs and sample results before publicizing.
- Some scans contain no embedded text and will need OCR in a future enhancement.
- The index is stored in the GitHub repository and published on GitHub Pages. Large archives can exceed GitHub's recommended repository size or Pages limits. If the JSON grows too large, split it by year or migrate to a dedicated search service.
- The crawler only traverses links on the official CDD domain, but may follow PDF links to the official site's document storage/CDN. It does not access restricted records.
- Titles and years are inferred from link text and filenames; verify dates against source PDFs.
- GitHub Actions scheduled runs may be delayed or disabled after prolonged repository inactivity.
- This archive is not an official record or a substitute for approved minutes.
