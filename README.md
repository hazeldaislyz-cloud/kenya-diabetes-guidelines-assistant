# Kenya diabetes guidelines assistant

Ask a question about diabetes care and get an answer taken only from Kenya's *National Clinical Guidelines on Management of Diabetes Mellitus* (Third Edition, 2024), with the page number for every fact. If the guideline doesn't cover the question, the assistant says so instead of guessing.

The guideline runs to 224 pages. A clinical officer at a busy health centre who needs the starting dose of basal insulin, or the potassium replacement in DKA, shouldn't have to search it page by page. Nor should they have to trust a chatbot that may be quoting another country's guideline or inventing a number. The design goal is narrow and testable: **answer from this document, show where, and refuse otherwise.**

## How it works

1. **Read the PDF.** Text is extracted page by page. Then every page is also read with OCR, because much of the guideline's most important content is in images. Where OCR finds substantial text that extraction missed, that text is added and marked as "read by OCR".
2. **Find the relevant passages** with BM25 keyword ranking. It runs offline, is easy to explain, and suits clinical questions, which turn on exact terms like HbA1c, eGFR or gliclazide. Words are normalised so British and American spellings (hypoglycaemia, hypoglycemia) and different word endings (screened, screening) match.
3. **Check the question is in scope before calling any model.** The gate weights each word by how rare it is in the guideline, so a word the guideline never uses (typhoid, cholera) counts heavily against the question, and generic words (treatment, dose) count for little. Low coverage means the answer is "not covered".
4. **Write the answer** with a language model (Claude), using only the retrieved passages, citing a page after every fact.
5. **Check the answer before showing it.** Every cited page must be one of the passages the model was given, and every fact must be cited. If not, the answer is withheld.
6. **Warn where the text may be wrong.** If the answer relies on OCR text, it ends with "Check the figure on page N before acting." If the question uses words the guideline never mentions, the answer says so.

Without an API key, the assistant runs offline and shows the best passages with their page numbers instead of a written answer.

## What I found in the guideline

**42 of the 224 pages carry content only in images.** That includes the treatment algorithm for type 2 diabetes in resource-scarce settings (metformin 500 mg, then gliclazide 80 mg, p. 44), insulin initiation (p. 48), the hypoglycaemia flowchart (p. 157) and the adult DKA pathway (p. 186). Plain text extraction reads none of it. Without OCR, the assistant couldn't answer the most basic prescribing question in the document.

**OCR misreads numbers, and in a clinical document that matters.** On p. 157, the glucagon dose for a child of "≥25 kg: 1 mg" was read as "225 kg: 1mg". That's why answers built on OCR text carry a warning to check the original figure.

**The guideline is not always consistent with itself.** Hypoglycaemia is "<3.9 mmol/L" in the flowchart on p. 157 and "below 4 mmol/L" in the annex on p. 209. DKA is defined as glucose over 13.9 mmol/L with bicarbonate under 18 on p. 182, but glucose over 11.0 with bicarbonate under 15 in the DKA pathway on p. 186. A summary that blended these would hide the conflict. Citing the page lets the health worker see which section an answer came from.

## Evaluation

I wrote 30 questions a health worker might ask, plus 6 the guideline doesn't cover. For every question I checked the answer against the page by hand: the key facts that must appear (doses, thresholds, intervals) and the pages that state them. I used this set to choose the relevance threshold. I then wrote a **separate held-out set** of 6 in-scope and 6 out-of-scope questions that played no part in any design choice, so the scores on it are an honest estimate of performance on new questions.

| Measure | Main set (36) | Held-out set (12) |
|---|---|---|
| Expected page among the top 5 passages | 93% | 67% |
| All key facts present in the top 5 passages | 93% | 83% |
| In-scope questions wrongly refused | 0% | 0% |
| Out-of-scope questions refused by the gate | 67% (4 of 6) | 33% (2 of 6) |
| Out-of-scope questions refused or flagged ("the guideline never mentions …") | 67% | 67% |

**What these numbers mean.** The retrieval step finds the evidence for most questions, and the gate never blocked a fair question. One fair question got a needless "never mentions" warning, because it used the word "afterwards". The weak point is off-topic questions that share real vocabulary with the guideline. Malaria, hepatitis, HPV vaccination and Pap smears all get past the gate, because the guideline does mention malaria, hepatitis, vaccines and smears in other contexts. For these, the language model is the second line of defence: it is told to answer only from the passages and reply "not covered" otherwise. The held-out set is small, so its percentages move a lot with each question.

**Questions it got wrong, and why:**

- *Eye screening interval in type 2 diabetes:* the answer (annually, p. 59) sits in a dense flowchart and lost out to pages about screening in general.
- *Metformin dose in chronic kidney disease:* p. 71 is a coloured chart that even OCR can't read. This is a real gap, and the answer would have to come from a person reading the figure.
- *Insulin infusion rate in adult DKA, HbA1c monitoring after basal insulin, glucose level in HHS:* the facts were found, but on a different page of the guideline from the one I expected, or not in the top 5.

**Not yet measured: the written answers.** Scoring the language model's answers (whether every key fact appears, whether the expected page is cited, how often the citation check withholds an answer) needs an Anthropic API key. Running `python -m guideassist.cli eval` with a key set adds those measures automatically. Until then, the results above cover retrieval and refusal, which run fully offline.

## Responsible use

- **It is not a clinician.** It finds and quotes the national guideline. The health worker decides.
- **No answer without a source.** Every fact must cite a page the model was actually given, or the answer is withheld. This is tested in `tests/test_guideassist.py`.
- **It refuses rather than guesses** when the guideline doesn't cover a question.
- **It flags its own weak spots:** answers that rely on OCR text, and questions using words the guideline never uses.
- **No patient data.** Questions are about the guideline, not about a person. Nothing is stored.

## Limitations

- One document only, and only the 2024 edition. When the guideline is updated, the index must be rebuilt.
- Keyword retrieval can miss a question phrased very differently from the guideline. Adding meaning-based (embedding) search alongside BM25 is the obvious next step.
- OCR text can be wrong, and some figures can't be read at all (p. 71).
- English only. Health workers in Kenya often think and talk in Kiswahili; a Kiswahili question would need translation first.
- The evaluation sets are small and written by one person. A real evaluation would use questions collected from health workers, and answers reviewed by a clinician.

## Next steps

1. Score the written answers with an API key, and have a clinician review a sample.
2. Collect 50 to 100 real questions from clinical officers and nurses, and re-run the evaluation on them.
3. Add embedding search and compare it with BM25 on the same questions.
4. Try it with Kiswahili questions.
5. Package it for low-bandwidth use: a WhatsApp or SMS front end, with the offline passage mode as the fallback.

## How to run

You need Python 3.10 or later. For OCR, install Tesseract too (`brew install tesseract` on a Mac, `sudo apt install tesseract-ocr` on Linux). Without it, the assistant still works but can't read text inside images.

The guideline PDF is not included in this repository. Get *National Clinical Guidelines on Management of Diabetes Mellitus, Third Edition 2024* from the Kenya Ministry of Health and save it as `data/guidelines.pdf`.

```bash
pip install -r requirements.txt
cd src
python -m guideassist.cli index ../data/guidelines.pdf   # about 3 minutes with OCR; builds data/passages.jsonl
python -m guideassist.cli ask "What is the starting dose of basal insulin in type 2 diabetes?"
python -m guideassist.cli eval                            # main question set
python -m guideassist.cli eval heldout                    # held-out question set
cd ..
python -m pytest tests                                    # 9 tests, no PDF or API key needed
```

To get written answers instead of passages, set `ANTHROPIC_API_KEY` before running `ask` or `eval`.

## Project layout

```
src/guideassist/
  ingest.py      PDF to page-tagged passages, with OCR for text inside images
  retrieve.py    BM25 search, spelling and word-ending normalisation, relevance coverage
  answer.py      relevance gate, prompt, citation check, OCR and unknown-word warnings
  evaluate.py    retrieval, refusal and (with an API key) answer scoring
  cli.py         index, ask, eval
eval/
  questions.jsonl  30 in-scope and 6 out-of-scope questions, answers checked by hand
  heldout.jsonl    6 + 6 questions kept back from all design choices
  summary*.json    latest scores
tests/           citation check, refusal, OCR warning, unknown-word warning
```

## Author

Daisy Mutegi. 13 years in medicine access and supply across East and Southern Africa (Novo Nordisk, Clinton Health Access Initiative), including helping Botswana's Ministry of Health develop its national diabetes treatment guidelines. [LinkedIn](https://linkedin.com/in/daisymutegi)

Built with the help of AI coding tools, which I used the way I'd expect a team to use them: I set the problem, the design and the evaluation, and checked the results.
