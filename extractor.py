"""
extractor.py - Extract text and images from PDF files using PyMuPDF
"""

import fitz  # PyMuPDF
import base64
import io
from typing import Dict, List, Any


def extract_pdf_content(pdf_bytes: bytes, pdf_name: str = "document") -> Dict[str, Any]:
    """
    Extract text and images from a PDF file.
    
    Returns a dict with:
      - text: full extracted text (string)
      - pages: list of per-page dicts with text + image refs
      - images: list of {page, index, b64, width, height, xref}
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    full_text_parts = []
    pages_data = []
    all_images = []
    image_counter = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # --- Text extraction ---
        page_text = page.get_text("text")
        full_text_parts.append(f"\n--- Page {page_num + 1} ---\n{page_text}")
        
        # --- Image extraction ---
        page_images = []
        image_list = page.get_images(full=True)
        
        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                img_ext = base_image.get("ext", "png")
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)
                
                # Skip tiny images (icons, decorators, masks < 50x50px)
                if width < 50 or height < 50:
                    continue
                
                # Convert to base64
                b64_str = base64.b64encode(image_bytes).decode("utf-8")
                mime = f"image/{img_ext}" if img_ext != "jpg" else "image/jpeg"
                
                img_record = {
                    "id": f"img_{image_counter}",
                    "source": pdf_name,
                    "page": page_num + 1,
                    "index_on_page": img_index,
                    "xref": xref,
                    "width": width,
                    "height": height,
                    "ext": img_ext,
                    "mime": mime,
                    "b64": b64_str,
                }
                
                all_images.append(img_record)
                page_images.append(img_record["id"])
                image_counter += 1
                
            except Exception as e:
                # Skip unextractable images silently
                continue
        
        pages_data.append({
            "page_num": page_num + 1,
            "text": page_text,
            "image_ids": page_images,
        })
    
    doc.close()
    
    return {
        "name": pdf_name,
        "total_pages": len(pages_data),
        "total_images": len(all_images),
        "text": "\n".join(full_text_parts),
        "pages": pages_data,
        "images": all_images,
    }


def build_image_map(images: List[Dict]) -> Dict[str, Dict]:
    """Build a quick lookup dict: image_id -> image record"""
    return {img["id"]: img for img in images}


def get_images_as_gemini_parts(images: List[Dict]) -> List[Dict]:
    """
    Return all extracted images sorted by page order.
    Images are not sent to the LLM — they are embedded directly
    in the HTML report by the renderer. No cap needed.
    """
    # Sort by page order so renderer distributes them correctly
    sorted_images = sorted(images, key=lambda x: x.get("page", 0))

    parts = []
    for img in sorted_images:
        parts.append({
            "inline_data": {
                "mime_type": img["mime"],
                "data": img["b64"],
            },
            "_img_id": img["id"],
            "_page": img["page"],
            "_source": img["source"],
        })

    return parts, sorted_images
