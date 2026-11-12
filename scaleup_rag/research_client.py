import re
import httpx
from typing import List, Dict, Optional, Callable
from .schemas import RequiredParameterSpec, RawExtractedCandidate, OperatingEnvelope

EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPE_PMC_XML_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"


def extract_operating_envelope(text: str, fallback_context: str = "") -> OperatingEnvelope:
    """Extract experimental temperature_c, ph, and pressure_bar from sentence or paragraph context."""
    def _scan(src: str) -> tuple[Optional[float], Optional[float], Optional[float]]:
        temp_c: Optional[float] = None
        ph_val: Optional[float] = None
        press_bar: Optional[float] = None

        t_m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:deg\s*C|[^\w\s.]?\s*C\b)", src)
        if t_m:
            try:
                temp_c = float(t_m.group(1))
            except ValueError:
                pass

        ph_m = re.search(r"\bpH\s*(?:=|:|of|was|at)?\s*([0-9]+(?:\.[0-9]+)?)", src, flags=re.IGNORECASE)
        if ph_m:
            try:
                v = float(ph_m.group(1))
                if 0.0 <= v <= 14.0:
                    ph_val = v
            except ValueError:
                pass

        p_m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*bar\b", src, flags=re.IGNORECASE)
        if p_m:
            try:
                press_bar = float(p_m.group(1))
            except ValueError:
                pass

        return temp_c, ph_val, press_bar

    t1, ph1, p1 = _scan(text)
    if fallback_context and (t1 is None or ph1 is None or p1 is None):
        t2, ph2, p2 = _scan(fallback_context)
        t1 = t1 if t1 is not None else t2
        ph1 = ph1 if ph1 is not None else ph2
        p1 = p1 if p1 is not None else p2

    return OperatingEnvelope(temperature_c=t1, ph=ph1, pressure_bar=p1)

def _strip_xml_tags(xml_text: str, max_chars: int = 12000) -> str:
    tables = re.findall(r"<table-wrap.*?>.*?</table-wrap>", xml_text, flags=re.DOTALL | re.IGNORECASE)
    body_match = re.search(r"<body.*?>(.*?)</body>", xml_text, flags=re.DOTALL | re.IGNORECASE)
    body_raw = body_match.group(1) if body_match else xml_text

    combined = "\n".join(tables) + "\n" + body_raw
    clean = re.sub(r"<[^>]+>", " ", combined)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_chars]

def search_europe_pmc(query: str, max_results: int = 5, fetch_fulltext: bool = False, timeout: float = 5.0) -> List[Dict]:
    params = {
        "query": query,
        "format": "json",
        "pageSize": max_results,
        "resultType": "core"
    }
    valid_papers = []
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(EUROPE_PMC_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("resultList", {}).get("result", [])

            for item in results:
                doi = item.get("doi")
                abstract = item.get("abstractText", "")
                pmcid = item.get("pmcid")
                is_oa = item.get("isOpenAccess") == "Y"

                if not doi or not abstract:
                    continue

                full_text_snippet = ""
                if fetch_fulltext and is_oa and pmcid:
                    try:
                        xml_resp = client.get(EUROPE_PMC_XML_URL.format(pmcid=pmcid), timeout=min(timeout, 3.0))
                        if xml_resp.status_code == 200:
                            full_text_snippet = _strip_xml_tags(xml_resp.text)
                    except Exception:
                        pass

                valid_papers.append({
                    "doi": doi,
                    "pmcid": pmcid,
                    "title": item.get("title", ""),
                    "abstractText": abstract,
                    "fullTextExcerpt": full_text_snippet
                })
    except Exception:
        pass

    return valid_papers

def extract_candidate_from_literature(
    spec: RequiredParameterSpec,
    papers: List[Dict],
    llm_extractor_fn: Optional[Callable[[RequiredParameterSpec, List[Dict]], Optional[RawExtractedCandidate]]] = None
) -> Optional[RawExtractedCandidate]:
    if llm_extractor_fn is not None:
        cand = llm_extractor_fn(spec, papers)
        if cand is not None:
            env_ctx = " ".join(
                f"{p.get('abstractText', '')} {p.get('fullTextExcerpt', '')[:1200]}"
                for p in papers
                if p.get("doi", "").strip() == cand.source_doi.strip()
            )
            extracted_env = extract_operating_envelope(cand.source_snippet, env_ctx)
            if cand.envelope.temperature_c is None:
                cand.envelope.temperature_c = extracted_env.temperature_c
            if cand.envelope.ph is None:
                cand.envelope.ph = extracted_env.ph
            if cand.envelope.pressure_bar is None:
                cand.envelope.pressure_bar = extracted_env.pressure_bar
        return cand
    return None
