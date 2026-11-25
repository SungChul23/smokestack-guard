Transcribe this page of a Korean legal document (statute, enforcement decree or rule, administrative notice, or an official handbook) into Markdown. The output is used for search and must be faithful to the page.

Rules:
1. Keep every Korean word, number, unit and symbol exactly as printed. Do not translate, summarize, paraphrase, correct, or add anything.
2. Remove page furniture only: running headers and footers such as "법제처 1 국가법령정보센터 <법령명>", page numbers, and repeated document titles printed at the top of every page.
3. Keep legal structure markers exactly: article numbers (제1조, 제17조의2), paragraphs (①, ②), items (1., 2.), sub-items (가., 나., 1), 가)), appendix labels ([별표 8], 별표 1의3), "(제○조 관련)", and amendment marks such as <개정 2026. 11. 4.> or [시행일: 2020. 1. 1.].
4. Tables: output a Markdown table that keeps the original column order and header text. When a cell spans several rows or columns, repeat its value in every covered cell so that each row can be read on its own. Keep values such as "50(6) 이하" exactly. Do not drop rows.
   - First count the printed columns from the vertical lines and the column positions of the values. Include columns whose header is blank and columns of a table that continues from the previous page.
   - The header row and every body row must have exactly that number of cells. Use an empty cell where the page shows no value. Never move a value into a neighbouring column, and never drop a value because it repeats the value next to it (for example "경 고 | 경 고 | 경 고" must stay three cells).
   - Before finishing, check each row: the number of cells equals the header, and each value sits under the same column it is printed under on the page.
5. If a heading or title shows each character twice (for example "굴굴뚝뚝 자자동동측측정정"), write each character once ("굴뚝 자동측정").
6. Use Markdown headings for chapter, section and appendix titles. Keep footnotes and 비고 (remarks) below the table they belong to.
7. If the page has no text (cover, blank, or image only), output nothing.
