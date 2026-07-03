# Informe Laboratorio 3

Archivo principal:

```bash
Informe_Laboratorio_3.tex
```

Para compilar en un equipo con LaTeX instalado:

```bash
pdflatex Informe_Laboratorio_3.tex
bibtex Informe_Laboratorio_3
pdflatex Informe_Laboratorio_3.tex
pdflatex Informe_Laboratorio_3.tex
```

En esta Raspberry no se detectó `pdflatex`, `xelatex` ni `latexmk`, por lo que el proyecto queda listo para compilar en Overleaf o en un equipo con TeX Live.
