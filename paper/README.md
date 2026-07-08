# Paper — two formats, same content

The full paper is provided two ways so you can produce a PDF without installing a
LaTeX toolchain.

## Quickest PDF (no installs) — `paper.html`
Open `paper.html` in any browser, then **Ctrl + P → Save as PDF** (margins:
Default). The on-screen banner is hidden in the print output. Figures load from
`figures/` next to the file, so keep them together.

## Publication-quality PDF — `main.tex` (LaTeX)
Compiles as-is; nothing exotic. Easiest path with zero local installs:
1. Go to [overleaf.com](https://www.overleaf.com) (free), **New Project → Upload
   Project**, and upload `main.tex` together with the `figures/` folder.
2. Click **Recompile**. Overleaf runs the LaTeX for you and produces the PDF.

Locally instead: `pdflatex main.tex` (twice, for references) if you have a TeX
distribution such as MiKTeX or TeX Live.

## Source of truth
Both documents are hand-written prose over the numbers in `../analysis/results.json`
and `../analysis/tables.md`, which regenerate from the committed logs. The
Markdown working draft is `../docs/paper.md`; citations were verified against
arXiv (2026-07-08).
