# Machines LaTeX 稿件

主文件：`a2rl_paper.tex`；编译结果：`a2rl_paper.pdf`。

采用用户提供的 MDPI 模板，文档选项为
`[machines,article,submit,moreauthors]`，保留投稿模式的行号。
`Definitions/` 从 `tougao_mdpi/Definitions/` 原样复制；本目录可独立编译。

在本目录运行：

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error a2rl_paper.tex
```

也可用 pdfLaTeX 连续编译，直至交叉引用稳定。参考文献直接保存在主文件的
`thebibliography` 中，不需要单独运行 BibTeX。

本次仅迁移模板与排版：保留原题名、作者、摘要文字、正文、公式、图注、
正文图片、表格数据及 34 条参考文献；移除摘要图片及 IEEE 专用模板文件。
原致谢中的资助与致谢两句话分别放入 MDPI 的 Funding 和 Acknowledgments。
附录按 MDPI 模板移至参考文献之前，参数表采用可分页的长表。

迁移前的完整文件夹已备份至同级目录：
`../Manuscript_latex_IEEE_backup_20260928_230628.zip`。
