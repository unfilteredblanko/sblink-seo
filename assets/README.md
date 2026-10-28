# SBLinkSEO brand assets

The product mark is a black square cut by a rising line, with a red corner arrow: a compact visual for discovering pages and following what comes next. The wordmark keeps SB Link in black and SEO in red.

- `sblinkseo-logo.png`: horizontal mark and wordmark, transparent background.
- `sblinkseo-banner.png`: white documentation masthead with the line “Your complete SEO house.”

Use the transparent logo on a light field. Keep its proportions and give it clear space on every side. The white masthead is suitable for a README in either a light or dark viewer. Avoid shadows, recoloring or placing the dark wordmark on a dark background.

The visual palette uses white, near-black and restrained red. Set accompanying text in a clean sans serif with readable spacing. The brand belongs to SB Link Network; see the repository license for reuse terms.

The report renderer packages a byte-identical copy of the logo in `src/sblinkseo/report_assets/` so installed wheels can export reports offline. A regression check prevents that copy from drifting. Report styling uses ink `#151515`, dark red `#991B1B`, white and neutral paper `#F5F3F1`; see [the report guide](../docs/branded-reports.md).
