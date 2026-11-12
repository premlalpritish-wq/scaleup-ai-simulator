import os
import re
import json
import httpx
from pathlib import Path
from typing import List, Dict, Optional
from .schemas import RequiredParameterSpec, RawExtractedCandidate
from .quarantine_gate import ureg
from .research_client import extract_operating_envelope

def _load_env_file():
    candidates = [
        Path(".env"),
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent / ".env"
    ]
    for env_path in candidates:
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass

_load_env_file()

def _call_json_llm(system_prompt: str, user_prompt: str) -> Optional[Dict]:
    _load_env_file()
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")

    try:
        # 1. Gemini / Google AI Studio API
        if gemini_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0}
            }
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, json=payload)
                if r.status_code == 200:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return json.loads(text)

        # 2. DeepSeek API
        if deepseek_key:
            headers = {"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"}
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0
            }
            with httpx.Client(timeout=30.0) as client:
                r = client.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload)
                if r.status_code == 200:
                    content = r.json()["choices"][0]["message"]["content"]
                    return json.loads(content)

        # 3. OpenAI or OpenAI-compatible Base URL
        if openai_key:
            base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1"
            base_url = base_url.rstrip("/")
            url = f"{base_url}/chat/completions"
            headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0
            }
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, headers=headers, json=payload)
                if r.status_code == 200:
                    content = r.json()["choices"][0]["message"]["content"]
                    return json.loads(content)

        # 4. Anthropic Claude API
        if anthropic_key:
            base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
            url = f"{base_url}/v1/messages"
            headers = {
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": "claude-3-5-sonnet-latest",
                "max_tokens": 2048,
                "temperature": 0.0,
                "system": system_prompt + "\nRespond ONLY with a valid raw JSON object.",
                "messages": [{"role": "user", "content": user_prompt}]
            }
            with httpx.Client(timeout=30.0) as client:
                r = client.post(url, headers=headers, json=payload)
                if r.status_code == 200:
                    text = r.json()["content"][0]["text"].strip()
                    if text.startswith("```"):
                        text = text.strip("`").removeprefix("json").strip()
                    return json.loads(text)
    except Exception:
        return None

    return None

def decompose_prompt_to_specs(prompt: str) -> List[RequiredParameterSpec]:
    system_prompt = (
        "You are ScaleUp's physical simulation parameter decomposer. "
        "Given a user prompt describing a physical product or bioprocess simulation, "
        "return a JSON object with key 'parameters' containing a list of required empirical parameters. "
        "Each item must match: "
        "{\"entity_name\": \"snake_case_name\", \"target_system\": \"species or material\", "
        "\"expected_unit\": \"Pint-parseable unit e.g. 'Pa * s', 'dimensionless', '1 / s', 'kg / m**3'\", "
        "\"envelope_constraints\": {\"temperature_c\": float_or_null, \"ph\": float_or_null, \"pressure_bar\": float_or_null}}"
    )
    data = _call_json_llm(system_prompt, prompt)
    if not data or "parameters" not in data:
        p_lower = prompt.lower()
        if "e. coli" in p_lower or "escherichia coli" in p_lower:
            return [
                RequiredParameterSpec(
                    entity_name="specific_growth_rate_mu_max",
                    target_system="Escherichia coli",
                    expected_unit="1 / hr"
                ),
                RequiredParameterSpec(
                    entity_name="yield_biomass_glucose",
                    target_system="Escherichia coli",
                    expected_unit="dimensionless"
                ),
                RequiredParameterSpec(
                    entity_name="maintenance_rate_m",
                    target_system="Escherichia coli",
                    expected_unit="1 / hr"
                ),
                RequiredParameterSpec(
                    entity_name="saturation_constant_ks",
                    target_system="Escherichia coli",
                    expected_unit="g / L"
                ),
                RequiredParameterSpec(
                    entity_name="mass_transfer_kla",
                    target_system="Escherichia coli",
                    expected_unit="1 / hr"
                ),
                RequiredParameterSpec(
                    entity_name="feed_glucose_concentration",
                    target_system="Escherichia coli",
                    expected_unit="kg / m**3"
                ),
                RequiredParameterSpec(
                    entity_name="oxygen_saturation_c_star",
                    target_system="Escherichia coli",
                    expected_unit="g / L"
                ),
                RequiredParameterSpec(
                    entity_name="oxygen_yield_yo",
                    target_system="Escherichia coli",
                    expected_unit="dimensionless"
                )
            ]
        elif "saccharina" in p_lower or "kelp" in p_lower or "alginate" in p_lower:
            return [
                RequiredParameterSpec(
                    entity_name="alginate_extraction_yield",
                    target_system="Saccharina latissima",
                    expected_unit="dimensionless"
                ),
                RequiredParameterSpec(
                    entity_name="dynamic_viscosity",
                    target_system="Saccharina latissima",
                    expected_unit="Pa * s"
                )
            ]
        elif "subtilis" in p_lower:
            return [
                RequiredParameterSpec(
                    entity_name="growth_rate",
                    target_system="Bacillus subtilis",
                    expected_unit="1 / hour"
                )
            ]
        return []
    return [RequiredParameterSpec(**item) for item in data["parameters"]]

def _normalize_regex_unit(unit_raw: str) -> str:
    u = unit_raw.strip().replace(" ", "").replace("^", "")
    replacements = {
        "h-1": "1 / hour",
        "hr-1": "1 / hour",
        "h⁻¹": "1 / hour",
        "1/h": "1 / hour",
        "/h": "1 / hour",
        "1/hr": "1 / hour",
        "/hr": "1 / hour",
        "s-1": "1 / second",
        "s⁻¹": "1 / second",
        "1/s": "1 / second",
        "/s": "1 / second",
        "d-1": "1 / day",
        "d⁻¹": "1 / day",
        "1/d": "1 / day",
        "/d": "1 / day",
        "h": "hour",
        "hr": "hour",
        "g/L": "g / L",
        "g/l": "g / L",
        "g/g": "dimensionless",
        "mmol/L": "mmol / L",
        "Pa*s": "Pa * s",
        "Pas": "Pa * s",
        "mPa*s": "mPa * s",
        "mPas": "mPa * s",
        "MPa": "MPa",
        "%": "percent"
    }
    return replacements.get(u, replacements.get(unit_raw.strip(), unit_raw))

def _extract_via_regex(spec: RequiredParameterSpec, papers: List[Dict]) -> Optional[RawExtractedCandidate]:
    """Deterministic extractor fallback that parses verified sentences from EuropePMC text."""
    stop_tokens = {"constant", "coefficient", "parameter", "value", "specific", "rate", "yield", "concentration"}
    raw_tokens = [t.lower() for t in spec.entity_name.split("_")]
    core_tokens = [t for t in raw_tokens if t not in stop_tokens]
    if not core_tokens:
        core_tokens = [raw_tokens[0]]

    try:
        target_unit_pint = ureg.Unit(spec.expected_unit)
    except Exception:
        return None

    for p in papers:
        doi = p.get("doi", "").strip()
        if not doi.startswith("10."):
            continue

        raw_text = (p.get("abstractText") or "") + " " + (p.get("fullTextExcerpt") or "")
        # Normalize HTML tags and superscripts before cleaning tags
        clean_text = re.sub(r"h\s*<sup>\s*-?1\s*</sup>", " h^-1", raw_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"h\s*<sup>\s*-?1", " h^-1", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"<sup>\s*-?1\s*</sup>", "^-1", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"<sup>\s*-?1", "^-1", clean_text, flags=re.IGNORECASE)
        clean_text = clean_text.replace("h⁻¹", " h^-1").replace("h-1", " h^-1")
        clean_text = re.sub(r"&[a-zA-Z0-9#]+;", " ", clean_text)
        clean_text = re.sub(r"<[^>]+>", " ", clean_text)
        clean_text = re.sub(r"[\u2000-\u200b\u00a0]", " ", clean_text)
        clean_text = re.sub(r"\s+", " ", clean_text)

        sentences = re.split(r"(?<=[.!?])\s+|\n+", clean_text)
        for sentence in sentences:
            s_clean = sentence.strip()
            if len(s_clean) < 15:
                continue

            s_lower = s_clean.lower()
            if not any(token in s_lower for token in core_tokens):
                continue

            # 1. Check plus-minus pattern: e.g. "0.50 ± 0.08 1/h" or "0.50 +/- 0.08 h^-1"
            pm_matches = re.finditer(
                r"([0-9]+(?:\.[0-9]+)?)\s*(?:\u00b1|\+/-|\ufffd)\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z0-9/%\*^⁻¹²³-]+)",
                s_clean
            )
            for m in pm_matches:
                val = float(m.group(1))
                err = float(m.group(2))
                unit_candidate = _normalize_regex_unit(m.group(3))
                try:
                    qty = ureg.Quantity(val, unit_candidate)
                    if qty.check(target_unit_pint.dimensionality):
                        return RawExtractedCandidate(
                            entity_name=spec.entity_name.lower(),
                            target_system=spec.target_system,
                            raw_value=val,
                            raw_value_min=round(val - err, 10),
                            raw_value_max=round(val + err, 10),
                            raw_unit=unit_candidate,
                            uncertainty=err,
                            envelope=extract_operating_envelope(s_clean, clean_text[:1200]),
                            source_doi=doi,
                            source_snippet=s_clean,
                            extraction_confidence=0.94
                        )
                except Exception:
                    continue

            # 2. Check range pattern: e.g. "0.42–0.58 h^-1", "0.42 - 0.58 1/h", "0.42 to 0.58 h^-1"
            range_matches = re.finditer(
                r"([0-9]+(?:\.[0-9]+)?)\s*(?:-|–|—|\bto\b)\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z0-9/%\*^⁻¹²³-]+)",
                s_clean,
                flags=re.IGNORECASE
            )
            for m in range_matches:
                v1 = float(m.group(1))
                v2 = float(m.group(2))
                v_min, v_max = min(v1, v2), max(v1, v2)
                v_mid = round((v_min + v_max) / 2.0, 10)
                unit_candidate = _normalize_regex_unit(m.group(3))
                try:
                    qty = ureg.Quantity(v_mid, unit_candidate)
                    if qty.check(target_unit_pint.dimensionality):
                        return RawExtractedCandidate(
                            entity_name=spec.entity_name.lower(),
                            target_system=spec.target_system,
                            raw_value=v_mid,
                            raw_value_min=v_min,
                            raw_value_max=v_max,
                            raw_unit=unit_candidate,
                            envelope=extract_operating_envelope(s_clean, clean_text[:1200]),
                            source_doi=doi,
                            source_snippet=s_clean,
                            extraction_confidence=0.93
                        )
                except Exception:
                    continue

            # 3. Scalar fallback: number + unit pattern
            matches = re.finditer(
                r"(?:of|=|\bat\b|reached\b|was\b)?\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z0-9/%\*^⁻¹²³-]+)",
                s_clean
            )
            for m in matches:
                val_str = m.group(1)
                unit_candidate = _normalize_regex_unit(m.group(2))
                try:
                    val = float(val_str)
                    qty = ureg.Quantity(val, unit_candidate)
                    if qty.check(target_unit_pint.dimensionality):
                        return RawExtractedCandidate(
                            entity_name=spec.entity_name.lower(),
                            target_system=spec.target_system,
                            raw_value=val,
                            raw_unit=unit_candidate,
                            envelope=extract_operating_envelope(s_clean, clean_text[:1200]),
                            source_doi=doi,
                            source_snippet=s_clean,
                            extraction_confidence=0.92
                        )
                except Exception:
                    continue

    return None

def live_llm_extractor(spec: RequiredParameterSpec, papers: List[Dict]) -> Optional[RawExtractedCandidate]:
    if not papers:
        return None

    corpus = []
    for p in papers:
        corpus.append(
            f"DOI: {p['doi']}\nTITLE: {p['title']}\nABSTRACT: {p['abstractText']}\n"
            f"FULLTEXT_EXCERPT: {p.get('fullTextExcerpt', '')[:4000]}\n---"
        )
    joined_corpus = "\n".join(corpus)

    system_prompt = (
        "You are ScaleUp's strict scientific literature parameter extractor. "
        "Examine the provided scientific papers and extract an explicit empirical numerical value for the requested parameter. "
        "EPISTEMIC RULE: If no explicit numerical value for this parameter is stated in the text, return {\"found\": false}. "
        "NEVER guess, estimate, or calculate a value not written in the text. "
        "If found, return JSON: "
        "{\"found\": true, \"candidate\": {\"entity_name\": str, \"target_system\": str, "
        "\"raw_value\": float, \"raw_value_min\": float_or_null, \"raw_value_max\": float_or_null, "
        "\"raw_unit\": str, \"uncertainty\": float_or_null, "
        "\"envelope\": {\"temperature_c\": float_or_null, \"ph\": float_or_null, \"pressure_bar\": float_or_null}, "
        "\"source_doi\": str, \"source_snippet\": \"exact verbatim sentence from the paper (>=15 chars)\", "
        "\"extraction_confidence\": float}}"
    )
    user_prompt = (
        f"Target Parameter: {spec.entity_name}\n"
        f"Target System/Species: {spec.target_system}\n"
        f"Expected Dimensional Unit: {spec.expected_unit}\n\n"
        f"Literature Corpus:\n{joined_corpus}"
    )

    data = _call_json_llm(system_prompt, user_prompt)
    if data and data.get("found") and "candidate" in data:
        try:
            return RawExtractedCandidate(**data["candidate"])
        except Exception:
            pass

    return _extract_via_regex(spec, papers)
