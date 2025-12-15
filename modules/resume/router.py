from fastapi import APIRouter, Response, HTTPException
from .schemas import RenderInput, RenderOutput, HtmlInput, RefineInput, RefineOutput
from .refiner import refine_profile_with_llm
from .renderer import render_html
from .exporters.pdf import html_to_pdf_bytes
from .exporters.docx import html_or_md_to_docx_bytes


router = APIRouter()


@router.post("/preview", response_model=RenderOutput)
def preview(input: RenderInput):
    return render_html(input)


@router.post(
    "/file/docx",
)
def generate_docx(input: RenderInput):
    html = render_html(input).html
    data = html_or_md_to_docx_bytes(html)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": "attachment; filename=resume.docx"
        },
    )


@router.post(
    "/file/pdf",
)
def generate_pdf(input: RenderInput):
    html = render_html(input).html
    try:
        data = html_to_pdf_bytes(html)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"PDF export unavailable: {e}")
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=resume.pdf"})


@router.post("/file/docx_from_html")
def generate_docx_from_html(input: HtmlInput):
    data = html_or_md_to_docx_bytes(input.html)
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.post("/refine", response_model=RefineOutput)
def refine(input: RefineInput):
    prof, summary, notes = refine_profile_with_llm(
        input.profile,
        input.jd,
        tone=input.options.tone,
        tense=input.options.tense,
        max_bullets_per_role=input.options.max_bullets_per_role,
        include_jd_keywords=input.options.include_jd_keywords,
    )
    return RefineOutput(profile=prof, summary=summary, notes=notes)
