import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from guideassist.answer import NOT_FOUND, answer, check  # noqa: E402
from guideassist.ingest import Passage, split_page  # noqa: E402
from guideassist.retrieve import Retriever  # noqa: E402

DOC = [
    Passage("a", 12, "Metformin is the first-line drug for type 2 diabetes. The starting dose of metformin is "
                     "500 mg once daily with meals, increased gradually to a maximum of 2 g per day."),
    Passage("b", 20, "Diagnose diabetes when fasting plasma glucose is 7.0 mmol/L or more, or HbA1c is 6.5% or more."),
    Passage("c", 31, "Treat hypoglycaemia below 4.0 mmol/L with 15 to 20 g of fast-acting glucose and recheck after 15 minutes."),
    Passage("d", 57, "Glucagon dose for severe hypoglycaemia: under 25 kg 0.5 mg, 25 kg and over 1 mg.", "ocr"),
] + [Passage(f"x{i}", 40 + i, f"Foot care advice for people with diabetes, section {i}, daily inspection of feet.")
     for i in range(5)]


class FakeClient:
    def __init__(self, text, stop_reason="end_turn"):
        self.text, self.stop, self.messages = text, stop_reason, self

    def create(self, **kw):
        return type("M", (), {"content": [type("C", (), {"text": self.text})()], "stop_reason": self.stop})()


def test_split_page_overlaps_and_keeps_page():
    ps = split_page(" ".join(f"w{i}" for i in range(400)), 7, max_words=180, overlap=40)
    assert all(p.page == 7 for p in ps)
    assert len(ps) == 3 and ps[1].text.split()[0] == "w140"


def test_retrieval_finds_right_page():
    r = Retriever(DOC)
    assert r.search("What HbA1c level confirms diabetes?", 1)[0][0].page == 20
    assert r.search("starting dose of metformin", 1)[0][0].page == 12


def test_citation_variants_are_read():
    from guideassist.answer import cited_pages
    assert cited_pages("x [p. 44, figure text, read by OCR] y") == {44}
    assert cited_pages("[pp. 43, 29] and (p. 66) and [p.12; p. 14]") == {43, 29, 66, 12, 14}
    assert cited_pages("[p. 182-183]") == {182, 183}
    assert cited_pages("no page here, 15 mg") == set()


def test_cut_off_answer_is_withheld():
    r = Retriever(DOC)
    res = answer("starting dose of metformin", r, client=FakeClient("Start metformin 500 mg [p. 12]. Then", "max_tokens"))
    assert res["answer"] == NOT_FOUND and "cut off" in res["source"]


def test_citation_check():
    assert check("Start 500 mg daily [p. 12].", {12, 20}) == []
    assert check("Start 500 mg daily.", {12}) == ["no citations"]
    assert "cites pages it was not given" in check("See [p. 99].", {12})[0]
    assert check(NOT_FOUND, {12}) == []


def test_answer_withheld_when_citation_invalid():
    r = Retriever(DOC)
    res = answer("starting dose of metformin", r, client=FakeClient("Start 1 g daily [p. 99]."))
    assert res["answer"] == NOT_FOUND and res["problems"]


def test_answer_passes_when_grounded():
    r = Retriever(DOC)
    res = answer("starting dose of metformin", r, client=FakeClient("Start metformin 500 mg once daily with meals [p. 12]."))
    assert res["source"] == "llm" and res["pages"] == [12]


def test_out_of_scope_refused_by_retrieval():
    r = Retriever(DOC)
    res = answer("What is the capital of France?", r, client=FakeClient("Paris [p. 12]."))
    assert res["answer"] == NOT_FOUND


def test_question_about_a_word_the_guideline_never_uses_is_flagged():
    r = Retriever(DOC)
    assert r.unknown_terms("starting dose of metformin for typhoid") == ["typhoid"]
    res = answer("starting dose of metformin for typhoid", r, client=FakeClient("Start metformin 500 mg once daily [p. 12]."))
    assert "never mentions: typhoid" in res["answer"]


def test_low_coverage_question_is_refused_without_calling_a_model():
    class Boom:
        messages = property(lambda self: (_ for _ in ()).throw(AssertionError("model should not be called")))
    r = Retriever(DOC)
    res = answer("How is cholera treated in children?", r, client=Boom())
    assert res["answer"] == NOT_FOUND


def test_answer_from_ocr_text_tells_reader_to_check_the_figure():
    r = Retriever(DOC)
    res = answer("glucagon dose for severe hypoglycaemia", r, client=FakeClient("Give 1 mg if 25 kg or over [p. 57]."))
    assert res["source"] == "llm" and "Check the figure on page 57" in res["answer"]
