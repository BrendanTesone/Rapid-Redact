"""Prompt templates for LLM-based CCI detection and document analysis."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.controllers.ai.llm_client import ChunkInfo
    from src.core.state.ai_state import CCILibraryItem
EMA_CCI_DEFINITION = """EMA Definition: Commercially Confidential Information (CCI) shall mean any information which is not in the public domain or publicly available and where its disclosure may undermine the economic interest or competitive position of the owner of the information.

EMA Examples of elements that may be considered CCI:
1. Exploratory objectives and endpoints
2. Information on the Quality and Manufacturing of medicines. A general principle regarding quality and manufacturing information is that detailed information could be considered commercially confidential but general information should be disclosed.
3. Composition and product development Information related to pharmaceutical development may be considered commercially confidential. This includes detailed data concerning the active substance, formulation, manufacturing, test procedures and validation (see Annex). The final qualitative formulation (composition) of the finished medicinal product is not CCI. The names of manufacturers and suppliers of the raw and starting materials, the excipients and the active substance may be considered CCI.
4. Active substance Information concerning the manufacturing of the active substance, including technical and industrial process parameters and in-process/intermediate specifications may be considered CCI. This applies to the final registered process and previous development processes. Detailed information on the synthesis or manufacture of the active substance, including details on the raw and starting materials, by-products and degradation products of active ingredients and validation of the manufacturing/synthesis process, may be considered CCI. Information on the structure of the active substance is not commercially confidential. This will be known and published at the time of allocating the international non-proprietary name (INN) if relevant. Detailed information concerning the particulars of polymorphism and particle size may be considered CCI. Concerning impurities and degradation products, qualitative and quantitative information may be considered CCI. A general description of the type of test methods used and the appropriateness of the specification is usually not CCI. However, detailed information on the test methods used and the specification and quantitative acceptance criteria established for the starting materials, intermediates and active substance may be considered CCI, unless it complies with the monographs in the European Pharmacopoeia or another national Pharmacopeia. In addition, for biotechnology products, a general description of the active ingredient including the type of molecule and its general structural features (e.g. number of amino acids, general glycosylation details) or of the type of producer cell (e.g. E. coli, S. cerevisiae, Chinese hamster ovary cells, Madin Darby kidney cells) is not CCI. Principles of the establishment of the Master Cell Bank (MCB) or Working Cell Bank (WCB) and on the stability of the cell banks are also not considered CCI. Principles of the fermentation and purification process are not CCI, although details including operating parameters and specific material requirements on Master Virus Seed (MVS), Master Seed Lot (MSL) and Master Transgenic Bank (MTB) may be considered CCI. Details on the process validation of the active substance manufacturing process may be considered CCI, although statements confirming that the manufacturing and control processes have been validated are not CCI. General information on the characterisation of the active substance such as the analytical technique(s) and statements confirming that the molecule is appropriately characterised are not considered CCI. However, details of characterisation technique(s) may be considered CCI. In general, storage conditions and shelf life of the active pharmaceutical ingredient (API) are not considered CCI. The above principles also apply to novel excipients.
5. Finished product. The detailed description of the manufacturing and control processes for the product may be CCI. This applies to the final registered process and previous development processes. Details of the validation of the manufacturing process may also be considered CCI. A general description of the type of test methods used and the appropriateness of the specification is not CCI. Detailed information on the test methods included in the specification of the finished product and the quantitative acceptance criteria may be CCI unless the tests are of Pharmacopoeial standard. In general, storage conditions and shelf life of the finished products are not considered CCI. Concerning degradation products, qualitative and quantitative information may be considered CCI.
6. Non-clinical and clinical information. Information encompassing non-clinical and clinical development of the medicinal product and the subsequent assessment by competent authorities is not per se commercially confidential. This includes information on environmental risk assessments with related studies and risk management plans. In general, data included in clinical study reports can be disclosed once has been anonymised. In exceptional and substantiated cases, consideration will be given to specific elements that may be commercially confidential.
7. Information on the outcome of inspections (e.g. conclusion on compliance/non compliance/outstanding issues to be addressed) is already available in the public domain (e.g. EudraGMDP and the European Public Assessment Report (EPAR)) and is therefore not considered commercially confidential. In exceptional cases where inspection-related information and documentation is provided by companies for the purpose of complying with applicable obligations, such information could be considered commercially confidential on a case-by-case basis and in line with the principles laid out in this guidance.
8. Detailed information on contractual agreements
9. Scientific advice. The disclosure of information on an agreed therapeutic indication should not be considered CCI after the finalisation of the related regulatory procedure. However, all the information related to further developments and new formulations which have not yet been part of a finalised regulatory procedure could be considered CCI. Information on future development plans such as the evaluation of new formulation or the investigation of the effect of the medicinal product in new indications or populations, details on studies which are part of ongoing Paediatric Investigation Plan (PIP), etc.

EMA Examples of elements NOT considered CCI:
1. Information already in the public domain, such as on:
   • Applicants'/MAHs' own web-site(s).
   • EMA web-site (product EPAR, scientific guidelines).
   • Clinical trials registries (such as EU Clinical Trials Register, ClinicalTrials.gov).
   • Web-sites of other regulatory authorities within the EU and outside the EU (such as FDA, PMDA, TGA, Health Canada) especially when the product (or another product containing the same active substance) is approved in those specific jurisdictions.
   • Scientific literature and articles (such as Textbooks, PubMed, Medline).
2. General or administrative information such as:
   • Study identification number(s) (e.g. EudraCT, ClinicalTrials.gov Identifier (NCT…), sponsor's internal study number).
   • Clinical Study Protocol Number and Title.
   • Names and addresses of investigator sites and the names of the principal investigators at each study site (unless it is mentioned in the context of individual patient data/case narratives and is deemed to constitute personal data.
   • Names of the countries where the clinical study is/was conducted (unless it is mentioned in the context of individual patient data/case narratives and is deemed to constitute personal data.
   • Number (how many) of study sites/research facilities were involved in the research
   • Name of the applicant's/MAH's own research facility(ies) where clinical studies were conducted (e.g. phase I studies).
   • Name of the trial sponsor or the legal entity (CRO) that acted as the clinical trial (CT) applicant on behalf of the sponsor.
   • Names of all CROs and vendors involved in trial-related duties and functions (e.g. central laboratories, IVRS provider, image reading centres, conduct of assays).
3. Quality-related information:
   • Structural formula of active metabolite(s) and metabolic pathway(s).
   • Lot/batch numbers of the investigational products understood as either test product, active comparator or placebo (excluding manufacturing site(s) IDs).
   • Excipient names which usually constitute publicly available information detailed in SmPCs.
   • Function of excipients as such information is widely available in the public domain.
   • Excipient batch numbers.
   • Even if a method of measurement is selected from several available methods, the name of the method or the combination of methods and their general description is not CCI.
   • High level safety-related information such as a virus inactivation process, ultrafiltration (removal of pyrogen), and the name of a purification process or the operation of a specific material.
   • The name of a cell line or strain with genetic recombination, when it is in commercial use or already published (e.g. CHO cell, E. Coli K-12).
   • Standard storage and shipping conditions of blood or tissue samples such as storage temperature or duration, which are described in related scientific guidelines (e.g. bioanalytical methods).
   • Temperature, humidity parameters, and storage duration as applied in stability tests.
4. Non-Clinical-related information
   • Information concerning a generally-used/well-known immunohistochemistry method (e.g. ELISA/LC-MS).
   • Drug concentration measurements including results.
   • The quantification range (lower and upper quantification limits) of pharmacokinetic and pharmacology tests/methods.
   • The name and high level description of test methods should not be redacted where a test is conducted based on a standard dissolution test/method referred to in scientific guidelines.
   • Information on radio-labelled molecules including information on the tagging site (unless it constitutes a novelty feature of the method developed by a company, as its disclosure would undermine the applicant's/MAH's legitimate economic interest).
5. Clinical-related information
   • Primary and secondary objectives including all Primary and secondary endpoints and timeframes (except for Exploratory).
   • Key Inclusion and exclusion criteria.
   • Duration of trial and number of planned enrolled patients.
   • Study design summary (study rationale).
   • Route of drug administration.
   • Study milestone dates such as study start date (first patient first visit), or primary completion date (last patient last visit).
   • Allowed concomitant medication(s).
   • Reasons for withdrawal.
   • Information on clinical data management (such as query resolution).
   • Information on the purpose and outcome of audits and inspections carried out during the conduct of clinical trials, including the audit plans.
   • Literature reviews, meta-analyses and pooled data analyses supporting certain study design elements or certain safety and efficacy claims.
   • Safety-related information such as adverse reactions (presented in various forms such as aggregated data or within case narratives) regardless of whether they are reflected in the approved product information or whether they were observed in clinical trials or reported after authorization.
   • Safety-related information/case narratives, even where the described case is related to "off label use" or reported from clinical studies conducted in other indications not yet applied for or approved.
   • Plasma drug concentration values and pharmacokinetic and pharmacodynamic parameters.

References Used:
External Guidance on the implementation of Policy 0070 (v1.5)
HMA-EMA guidance"""

CCI_DETECTION_SYSTEM_ROLE = (
    """You are a CCI detection assistant for clinical trial documents."""
)

CCI_DETECTION_TASK = """Your task: Find Company Confidential Information (CCI) in the PDF text by comparing it to the CCI library examples below AND applying the EMA CCI definition above. Look for text that matches the patterns, categories, and types shown in the library, while following the EMA guidelines for what IS and IS NOT CCI.

IMPORTANT: Apply the detection rules thoroughly. When uncertain whether information meets the CCI criteria, consider whether disclosure could undermine competitive position or reveal non-public development strategy."""

CCI_DETECTION_RULES = """DETECTION RULES:

Rule 1 - BIOMARKER AND SCIENTIFIC STRATEGY RULE:
Flag as potential CCI if the text references biomarkers, analytes, molecular targets, cytokines, genetic or immunogenicity markers, target-engagement markers, assay designs, molecular characterization, binding properties, epitopes, receptor interactions, or other study-specific scientific measurements that could reveal non-public compound characterization, mechanism of action, target biology, biomarker strategy, patient stratification, exploratory research, or development strategy, including when presented as glossary terms, acronym definitions, abbreviations, or schedule table entries.

Rule 2 - TREATMENT AND OPERATIONAL STRATEGY RULE:
Flag as potential CCI if the text reveals non-public treatment strategy, treatment administration, dosing strategy, dose-selection rationale, dose justification, treatment schedules, visit schedules, cycle structures, monitoring requirements, sample collection requirements, treatment sequencing, exposure periods, comparator-specific procedures, assessment schedules, or other operational study details that could reveal how the investigational product is administered, evaluated, differentiated, or developed.
Rule 3 - SPONSOR PERSONNEL AND INTERNAL IDENTITY RULE:
Flag as potential CCI if the text identifies sponsor employees, contractors, or internal personnel through names, signatures, initials, email addresses, approval records, electronic signatures, organizational roles, reporting structures, or department information, particularly in cover pages, approval pages, amendment histories, and signature sections.
Rule 4 - STATISTICAL DESIGN AND EXECUTION RULE:
Flag as potential CCI if the text discloses study-specific statistical design details, including sample-size assumptions, endpoint variability estimates, measurement precision assumptions, screening or retention assumptions, power calculations, event projections, hazard ratio thresholds, stopping criteria, decision rules, endpoint dependencies, analysis timing, modeling assumptions, event-triggered analyses, projected outcomes, formulas, or other non-public statistical assumptions used to design, power, or execute the study.
Rule 5 - SECTION CONTEXT RULE:
Use bookmarks, headings, table titles, figure titles, appendix titles, and section context to lower the detection threshold for content matching other rules, particularly within sections related to study design, treatment schedules, dosing, study procedures, PK, PD, biomarkers, genetics, immunogenicity, exploratory objectives, exploratory analyses, efficacy analyses, or statistical design; apply heightened scrutiny to biomarker collections, PK/PD collections, immunogenicity assessments, exploratory assessments, assay-related procedures, treatment-monitoring activities, and similar content within Schedule of Activities or Schedule of Events tables. Tables are marked with [TABLE START] and [TABLE END] tags. Within tables, [HEADER] indicates column headers and [ROW] indicates data rows. If a biomarker or assessment appears as a [ROW] label in a Schedule table, it likely indicates that biomarker will be collected as part of the study.
Rule 6 - DEVELOPMENT STRATEGY RULE:
Flag as potential CCI if the text discloses non-public development plans, investigational hypotheses, research rationale, development strategy, patient-selection strategy, endpoint strategy, comparator strategy, future indications, future populations, future development programs, planned companion studies, lifecycle management strategies, or other information revealing how the sponsor intends to develop, evaluate, position, or differentiate the investigational product.
Rule 7 - COMPETITIVE POSITIONING AND EXPLORATORY RESEARCH RULE:
Flag as potential CCI if the text contains competitor comparisons, superiority claims, competitive positioning statements, comparative product evaluations, exploratory objectives, exploratory endpoints, exploratory analyses, exploratory biomarkers, exploratory assays, or exploratory research questions that reveal non-public investigational priorities, scientific interests, or development strategy.
Rule 8 - REGULATORY STRATEGY AND ADVICE RULE:
Flag as potential CCI if the text discloses non-public regulatory interactions, scientific advice, agency feedback, regulatory strategy, regulatory commitments, development negotiations, or guidance received from regulatory authorities.
Rule 9 - INNOVATIVE METHODS RULE:
Flag as potential CCI if the text describes novel, proprietary, sponsor-specific, or innovative analytical methods, scientific methods, assay techniques, assessment approaches, scoring methodologies, questionnaire scoring calculations, PRO scoring logic, custom endpoint derivations, or other non-public methodologies that could reveal competitive advantage.
EXCLUSION RULE - ADMINISTRATIVE AND DOCUMENT CONTROL INFORMATION:
Do not flag protocol numbers, amendment numbers, IND numbers, EudraCT numbers, EU CT numbers, workflow IDs, approval IDs, document control numbers, version numbers, publication IDs, document identifiers, approval timestamps, generated metadata, document lifecycle information, system-generated tracking information, study milestone dates, routine regulatory identifiers, or similar administrative content unless the text also contains independently sensitive information covered by another detection rule.

DECISION PRINCIPLE:
When uncertain, favor recall. However, every detection must have a clear link to:
1. The EMA definition of CCI,
2. A pattern represented in the CCI library, or
3. One of the detection rules above.

Do not flag generic clinical, administrative, regulatory, public-domain, or document-control information unless it also reveals non-public scientific strategy, treatment strategy, development strategy, statistical design, sponsor personnel information, or other commercially sensitive content.
"""

TABLE_INTERPRETATION_GUIDE = """
=== INTERPRETING TABLE STRUCTURE ===

Tables appear twice:
1. Original PDF text (linearized) - searchable
2. Structured representation with [TABLE START], [HEADER], [ROW] tags - for understanding structure

Structured format:
  [TABLE START: X columns x Y rows]
  [HEADER] Column1 | Column2 | Column3
  [ROW] RowLabel | Cell1 | Cell2
  [TABLE END]

[HEADER] rows define column meanings; [ROW] labels identify what is measured.

CRITICAL: When reporting CCI from tables, return ORIGINAL TEXT as it appears in the PDF, NOT the formatted representation.

Example:
Original text: "IL-6 Analysis X X"
Structured: [ROW] IL-6 Analysis | X | - | X
Return: {"text": "IL-6 Analysis", ...}
"""

OlD_CCI_DETECTION_RULES = """DETECTION RULES:

Rule 1 - BIOMARKER AND SCIENTIFIC STRATEGY RULE: Flag as potential CCI if the text references, defines, expands, describes, measures, analyzes, or evaluates a specific biomarker, analyte, molecular target, cytokine, genetic marker, immunogenicity marker, pharmacokinetic parameter, pharmacodynamic parameter, assay variable, or target-engagement marker that could reveal non-public compound characterization, mechanism of action, target biology, target engagement, patient stratification, biomarker strategy, or development strategy. Biomarker and molecular-target terms should be flagged even when they appear only as glossary entries, acronym definitions, abbreviation expansions, lists of terms, or terminology references, if the biomarker, analyte, molecular target, cytokine, or assay is used elsewhere in the study.

Rule 2 - TREATMENT STRATEGY RULE: Flag as potential CCI if the text reveals non-public treatment strategy, study design, treatment administration, arm-specific procedures, treatment schedules, dosing schedules, visit schedules, cycle structures, monitoring requirements, sample collection requirements, treatment sequencing, exposure periods, comparator-specific procedures, or other information that could reveal how the investigational product is administered, evaluated, differentiated, or operationalized within the study.

Rule 3 - SPONSOR PERSONNEL RULE: Flag as potential CCI if the text identifies sponsor employees or contractors through names, signatures, initials, email addresses, approval records, electronic signature information, department names, reporting roles, or organizational titles. Apply heightened scrutiny to cover pages, signature pages, amendment histories, and the first or last pages of a document.

Rule 4 - STATISTICAL DESIGN AND EXECUTION RULE: Flag as potential CCI if the text appears within or references sections related to statistical analysis, sample size determination, efficacy analyses, endpoint testing, interim analyses, survival analyses, or statistical analysis plans, and discloses non-public statistical assumptions, power calculations, event projections, hazard ratio thresholds, information fractions, stopping criteria, decision rules, endpoint dependencies, analysis timing, study execution criteria, modeling assumptions, event-triggered analyses, projected outcomes, formulas, or other study-specific statistical design details.

Rule 5 - SECTION CONTEXT RULE: Section context matters. If a bookmark, heading, appendix title, table title, figure title, or section name indicates a sensitive category such as Schedule of Activities, Treatment Period, Study Procedures, Treatment Administration, Dosing, Assessments, Monitoring, Follow-Up, Visit Schedule, Schedule of Events, PK, PD, Biomarkers, Genetics, Immunogenicity, Exploratory Objectives, Statistical Considerations, Sample Size Determination, Interim Analysis, Efficacy Analysis, Study Design, or Statistical Analysis Plan, lower the threshold for flagging content within that section. If text occurs in a Schedule of Activities / Schedule of Events treatment table, strongly favor flagging.

Rule 6 - DEVELOPMENT STRATEGY RULE: Flag as potential CCI if the text discloses non-public study objectives, endpoint strategies, investigational hypotheses, development rationale, mechanism-based research plans, future research activities, comparator strategy, patient selection strategy, or other information that reveals how the sponsor intends to evaluate, position, develop, or differentiate the investigational product.

Rule 7 - COMPETITIVE COMPARISON AND EXPLORATORY OBJECTIVES RULE: Flag as potential CCI if the text contains comparisons to competitor products, claims of superiority, statements asserting advantages over alternative treatments, or competitive positioning language. Also flag any text describing exploratory objectives, exploratory endpoints, or exploratory analyses that reveal non-public investigational priorities or research questions.


EXCLUSION RULE 1 - ADMINISTRATIVE IDENTIFIERS: Do not flag administrative, regulatory, tracking, workflow, or document-management identifiers that do not disclose study strategy, scientific methodology, treatment strategy, biomarker strategy, statistical design, manufacturing information, sponsor personnel details, or development plans. Examples include protocol numbers, amendment numbers, IND numbers, EudraCT/EU CT numbers, workflow IDs, approval IDs, document control numbers, version identifiers, approval timestamps, and system-generated tracking metadata.

EXCLUSION RULE 2 - DOCUMENT CONTROL METADATA: Do not flag document control identifiers, approval timestamps, version numbers, workflow IDs, publication IDs, generated document identifiers, document lifecycle metadata, system-generated approval records, or similar administrative tracking information unless the text also contains sponsor personnel details, email addresses, signatures, organizational roles, or other independently sensitive information."""

CCI_DETECTION_INSTRUCTIONS = """
CCI SCREENING TEST:

Information is more likely to be CCI if one or more of the following apply:
• It is not publicly available.
• It is innovative, novel, or competitively differentiating.
• It is specific to the sponsor's development approach.
• It supports exploratory research or future development plans.
• It reflects sensitive regulatory interactions or advice.
• Disclosure could provide competitors insight into scientific, operational, or development strategy.

When evaluating uncertain text, explicitly consider these factors.

INSTRUCTIONS:
1. Review the CCI library examples above to understand what types of information to look for
2. Scan the PDF text below for similar confidential information
3. Be aggressive - flag anything that could potentially be CCI, even if uncertain
4. Return ONLY text that closely matches the library examples in nature and sensitivity
5. Each detection must include the exact page number where it appears
6. Return an empty array [] if you don't find any CCI"""

CCI_DETECTION_OUTPUT_FORMAT = """Return JSON array in this exact format:
[
  {{
    "text": "short specific phrase from the PDF",
    "page": page_number (must be between {start_page} and {end_page}),
    "confidence": "high",
    "category": "category from library examples",
    "justification": "brief explanation of why this matches the library pattern",
    "context": "surrounding text (50-100 words)"
  }}
]

Return [] if no CCI found."""


def build_cci_detection_prompt(
    pdf_text: str,
    cci_library: list["CCILibraryItem"],
    chunk_info: "ChunkInfo",
) -> str:
    """Build the main CCI detection prompt."""
    library_text = _format_library(cci_library)

    library_section = (
        f"""CCI Library (examples of what to look for):
{library_text}

"""
        if library_text
        else ""
    )

    section_label = (
        f"Section: {chunk_info['section_title']}\n"
        if chunk_info.get("section_title")
        else ""
    )

    doc_context_section = ""
    doc_ctx = chunk_info.get("doc_context")
    if doc_ctx:
        parts = ["DOCUMENT CONTEXT:"]
        if doc_ctx.get("doc_type"):
            parts.append(f"Type: {doc_ctx['doc_type']}")
        if doc_ctx.get("doc_title"):
            parts.append(f"Title: {doc_ctx['doc_title']}")
        if doc_ctx.get("summary"):
            parts.append(f"Summary: {doc_ctx['summary']}")
        if doc_ctx.get("toc_summary"):
            parts.append(f"\nDocument Outline (TOC):\n{doc_ctx['toc_summary']}")
        if doc_ctx.get("table_inventory"):
            parts.append(f"\nTable Inventory:\n{doc_ctx['table_inventory']}")
        if doc_ctx.get("title_page_text"):
            parts.append(f"\nTitle Page (verbatim):\n{doc_ctx['title_page_text']}")
        if doc_ctx.get("toc_text"):
            parts.append(f"\nTable of Contents (verbatim):\n{doc_ctx['toc_text']}")
        doc_context_section = "\n".join(parts) + "\n\n"

    output_format = CCI_DETECTION_OUTPUT_FORMAT.format(
        start_page=chunk_info["start_page"], end_page=chunk_info["end_page"]
    )

    return f"""{CCI_DETECTION_SYSTEM_ROLE}

{doc_context_section}{EMA_CCI_DEFINITION}

{CCI_DETECTION_TASK}

{CCI_DETECTION_RULES}

{TABLE_INTERPRETATION_GUIDE}

{library_section}{CCI_DETECTION_INSTRUCTIONS}

PDF Text to Analyze (File: {chunk_info['file_name']}, {section_label}Pages: {chunk_info['start_page']}-{chunk_info['end_page']}):
{pdf_text}

{output_format}"""


def build_document_summary_prompt(
    title_page_text: str,
    toc_text: str,
    pdf_metadata_title: str,
) -> str:
    """Build prompt for document summarization (title, type, summary, compound)."""
    combined_text = ""
    if pdf_metadata_title:
        combined_text += f"PDF Metadata Title: {pdf_metadata_title}\n\n"
    if title_page_text:
        combined_text += f"Title Page Text:\n{title_page_text}\n\n"
    if toc_text:
        combined_text += f"Table of Contents Text:\n{toc_text}"

    return f"""You are analyzing a clinical/regulatory document. Based on the title page and table of contents below, extract:
1. The document title (exact title as written, or best approximation)
2. The document type (e.g. Clinical Study Report, Protocol, Investigator Brochure, Informed Consent Form, Statistical Analysis Plan, etc.)
3. A 2-4 sentence summary of what this document covers
4. The primary compound/drug name being studied (if identifiable)

{combined_text}

Respond with ONLY a JSON object (no markdown fences):
{{
  "doc_title": "exact title",
  "doc_type": "document type",
  "summary": "2-4 sentence summary",
  "compound_name": "primary compound name or empty string if not found"
}}"""


def _format_library(library: list["CCILibraryItem"]) -> str:
    """Format CCI library for prompt inclusion."""
    lines = []
    for entry in library:
        lines.append(f"- Text: \"{entry['redacted_text']}\"")
        lines.append(f"  Context: \"{entry['context']}\"")
        lines.append(f"  Category: {entry['category']}")
        lines.append(f"  Justification: {entry['justification']}")
        lines.append("")
    return "\n".join(lines)
