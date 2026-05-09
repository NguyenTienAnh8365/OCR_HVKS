"""LaTeX preamble + postamble dùng cho XeLaTeX."""


LATEX_PREAMBLE = r"""\documentclass[12pt,a4paper]{article}
\usepackage{fontspec}
\defaultfontfeatures{Ligatures=TeX}
\setmainfont{DejaVu Serif}
\setsansfont{DejaVu Sans}
\setmonofont{DejaVu Sans Mono}
\usepackage[margin=2.2cm]{geometry}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage{array,booktabs,longtable}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{parskip}
\usepackage{soul}
\setlength{\parindent}{0pt}
\setuldepth{strut}
\newcommand{\headerpair}[2]{%
\noindent
\begin{minipage}[t]{0.48\textwidth}
\centering\small
#1\par
\end{minipage}\hfill
\begin{minipage}[t]{0.48\textwidth}
\centering\small
#2\par
\end{minipage}
\vspace{0.35cm}}
\newcommand{\formtitle}[1]{%
\vspace{0.3cm}
\begin{center}
\textbf{\large\MakeUppercase{#1}}
\end{center}
\vspace{0.2cm}}
\newcommand{\signaturepair}[6]{%
\vspace{0.8cm}
\noindent
\begin{minipage}[t]{0.46\textwidth}
\centering
\textbf{#1}\par
\vspace{0.1cm}
#2\par
\vspace{1.8cm}
{\textit{#3}\par}
\end{minipage}\hfill
\begin{minipage}[t]{0.46\textwidth}
\centering
\textbf{#4}\par
\vspace{0.1cm}
#5\par
\vspace{1.8cm}
{\textit{#6}\par}
\end{minipage}}
\newcommand{\pagenote}[1]{\begin{center}#1\end{center}}
\begin{document}
"""

LATEX_POSTAMBLE = "\n\\end{document}\n"


def build_full_tex(body: str) -> str:
    return LATEX_PREAMBLE + body.strip() + LATEX_POSTAMBLE
