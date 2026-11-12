import streamlit as st
import requests
import pandas as pd
from io import BytesIO
from typing import List, Optional, Dict
import json
from pydantic import BaseModel, Field
from pprint import pprint
import os
os.environ["AZURE_OPENAI_API_KEY"] = '1upMG076tp2LECi2y1aGMSN9KGsMmFpY5HuZYArBVzKS2TnQkrvsJQQJ99BCACHYHv6XJ3w3AAABACOGRjUa'
from openai import AzureOpenAI

client = AzureOpenAI(
    api_version="2023-07-01-preview",
    azure_endpoint="https://journey-automation.openai.azure.com",
    api_key=os.environ["AZURE_OPENAI_API_KEY"]
)

# ── Session state init ─────────────────────────────────────────────────────────
if 'page' not in st.session_state:
    st.session_state.page = 'page1'
if 'username' not in st.session_state:
    st.session_state.username = ''
if 'dbPointer' not in st.session_state:
    st.session_state.dbPointer = ''
if 'journey_desc' not in st.session_state:
    st.session_state['journey_desc'] = ""

# ── Navigation helpers ─────────────────────────────────────────────────────────
def go_to_page2():
    st.session_state.page = 'page2'
    st.rerun()

def go_to_page3():
    st.session_state.page = 'page3'
    st.rerun()

def go_to_page1():
    st.session_state.page = 'page1'
    st.rerun()


# ── Pydantic models ────────────────────────────────────────────────────────────
class journeyitems(BaseModel):
    providerContentId: str = Field(..., alias='providerContentId', description='providerContentId')
    Title: str = Field(..., alias='Title', description='Title of the chosen item')
    Description: str = Field(..., alias='Description', description='Description of the chosen item')
    duration: str = Field(..., alias='duration', description='duration of the chosen item')
    content_type: str = Field(..., alias='content_type', description='content_type of the chosen item')
    reason: str = Field(..., alias='reason', description='reason why the item was chosen')

class ExtractedInfo(BaseModel):
    journey: List[journeyitems] = Field(..., description='Give the learning journey in sequence of contents')


# ── Proficiency Level mapping (DB numeric → label) ────────────────────────────
COMPETENCY_LEVEL_MAP = {
    1: "Novice",
    2: "Emerging",
    3: "Intermediate",
    4: "Advanced",
    5: "Expert"
}

# ── Valid filter value mappings (shared across single + bulk) ─────────────────
DURATION_MAP = {
    "Long 20+ mins":    "1200 - 0",
    "Medium 4-20 mins": "240 - 1200",
    "Short 0-4 mins":   "0-240"
}
LANGUAGE_MAP = {
    "English":          "en",
    "Arabic":           "ar",
    "Bahasa Indonesia": "bh-ind"
}
CONTENT_TYPE_MAP = {
    "Artefact": "artifact",
    "Module":   "module"
}
ARTEFACT_MAP = {
    "Article": "article",
    "Podcast": "podcast",
    "Video":   "video"
}
PL_OPTIONS = ["Novice", "Emerging", "Intermediate", "Advanced", "Expert"]


# ── Search API ─────────────────────────────────────────────────────────────────
def searchapi(accessToken, skillName, duration, language, content_type, artefact_type):
    searchApiUrl = 'https://searchservice-msvc-india.disprz.com/v1/trainer-search/learning-items'
    headers = {'Content-Type': 'application/json', 'Access-Token': accessToken}

    language_filter = {"fieldName": "language_codes", "options": [], "searchTerm": "", "isTruncated": False}
    for lf in language:
        if lf == 'en':
            language_filter['options'].append({"count": 0, "from": 0, "to": 0, "type": "normal", "label": "English (UK)", "value": "en"})
        elif lf == 'ar':
            language_filter['options'].append({"count": 0, "from": 0, "to": 0, "type": "normal", "label": "Arabic (العربية)", "value": "ar"})
        elif lf == 'bh-ind':
            language_filter['options'].append({"count": 0, "from": 0, "to": 0, "type": "normal", "label": "Bahasa Indonesia", "value": "bh-ind"})

    duration_filter = {"fieldName": "duration_in_sec", "options": [], "searchTerm": "", "isTruncated": False}
    for df_ in duration:
        if df_ == '1200 - 0':
            duration_filter['options'].append({"count": 0, "from": 1200, "to": 0, "type": "range", "label": "Long 20+ mins", "value": "1200 - 0"})
        elif df_ == '240 - 1200':
            duration_filter['options'].append({"count": 0, "from": 240, "to": 1200, "type": "range", "label": "Medium 4-20mins", "value": "240 - 1200"})
        elif df_ == '0-240':
            duration_filter['options'].append({"count": 0, "from": 0, "to": 240, "type": "normal", "label": "Short 0-4mins", "value": "0-240"})

    artefact_filter = {"fieldName": "content_type.keyword", "options": []}
    for af in artefact_type:
        if af in ('article', 'podcast', 'video'):
            artefact_filter['options'].append({"count": 0, "from": 0, "to": 0, "type": "normal", "label": af, "value": af})

    data = {
        "term": skillName, "size": 50, "skip": 0,
        "sortDirection": "asc", "includeFacets": True,
        "sortBy": "relevance", "filters": []
    }
    if language_filter['options']:
        data['filters'].append(language_filter)
    if duration_filter['options']:
        data['filters'].append(duration_filter)
    if len(content_type) == 1:
        ct_val   = content_type[0]
        ct_label = "Artifacts" if ct_val == "artifact" else "modules"
        data['filters'].append({
            "fieldName": "type",
            "options": [{"type": "normal", "label": ct_label, "value": ct_val}],
            "searchTerm": "", "isTruncated": False
        })
    if artefact_filter['options']:
        data['filters'].append(artefact_filter)

    response = requests.post(searchApiUrl, headers=headers, json=data)
    if response.status_code == 200:
        filtered_data = []
        for item in response.json()['hits']:
            if item.get("removedOn") is None:
                competency_num = item.get("contentCompetencyLevel", None)
                filtered_data.append({
                    "id":                item["id"],
                    "name":              item["name"],
                    "description":       item.get("description", ""),
                    "duration":          item["duration"],
                    "providerName":      item["providerName"],
                    "content_type":      item['type'],
                    "proficiency_level": COMPETENCY_LEVEL_MAP.get(competency_num, "Not Specified")
                })
        return json.dumps(filtered_data, indent=4)
    else:
        print(f'Error: {response.status_code} - {response.text}')
        return None


# ── GPT helpers ────────────────────────────────────────────────────────────────
def get_completion(context, prompt):
    messages = [{"role": "system", "content": context}, {"role": "user", "content": prompt}]
    response = client.chat.completions.create(
        model="gpt-4o", messages=messages, temperature=0.5,
        functions=[{"name": "Learning_Journey_Curator", "parameters": ExtractedInfo.model_json_schema()}],
        function_call={"name": "Learning_Journey_Curator"}
    )
    return response.choices[0].message.function_call.arguments

def get_completion_desc(context, prompt):
    messages = [{"role": "system", "content": context}, {"role": "user", "content": prompt}]
    response = client.chat.completions.create(model="gpt-4o", messages=messages, temperature=0.5)
    return response.choices[0].message.content


# ── Prompt builder ─────────────────────────────────────────────────────────────
def build_context(length, skill_name, json_data, designation=None, industry=None, target_pl=None):
    if target_pl:
        pl_levels = ", ".join(target_pl)
        pl_instruction = (
            f"11. The learning journey is targeted at the following proficiency level(s): {pl_levels}. "
            f"Each content item already has a 'proficiency_level' field from the database. "
            f"Prioritise and prefer selecting content whose 'proficiency_level' matches: {pl_levels}. "
            f"Only include content outside these levels if there is not enough relevant content at the target level(s)."
        )
    else:
        pl_instruction = (
            "11. No target proficiency level was specified. Select the most relevant content regardless of proficiency level. "
            "Try to provide a good progression across proficiency levels where possible."
        )

    base_rules = """
                Strictly follow these rules:
                1. Parse through the entire content library in JSON format (from first to last) and select only content from the provided content library.
                2. Ensure that the content is actually relevant to the skill {skill_name}{persona_suffix}. Sometimes the content library has irrelevant content. Include only content that is highly and directly relevant to the skill in the journey.
                3. Provide a good progression of learning content.
                4. Shuffle and pick the learning content; do not give content exactly in the order it appears in the content library.
                5. The learning journey should have a good mix of content from all the content providers in the ContentLibrary.
                6. Ensure you do not return content with the same title names in the journey.
                7. Ensure that you pick {length} different modules. Do not return duplicate content even if they have different content IDs. If {length} highly relevant content modules are not available, then you can return fewer.
                8. If none of the content in the content library matches the skill {skill_name}{persona_suffix}, return null.
                9. Do not hallucinate and provide random courses that are not present in the content library.
                10. The response should strictly be in this format: [{{"providerContentId": , "Title": , "Description": , "duration": , "content_type": , "reason": }}]. Do not return any additional text.
                {pl_instruction}

                ###
                {json_data}
                ###
            """

    if designation and industry:
        intro          = f"Create a journey consisting of {{length}} learning modules from the content library provided below, delimited by ###, for the skill {{skill_name}} aligned to the '{{designation}}' designation working in the '{{industry}}' industry."
        persona_suffix = f", {{designation}} designation and {{industry}} industry"
    elif designation:
        intro          = f"Create a journey consisting of {{length}} learning modules from the content library provided below, delimited by ###, for the skill {{skill_name}} aligned to the '{{designation}}' designation."
        persona_suffix = f" and {{designation}} designation"
    elif industry:
        intro          = f"Create a journey consisting of {{length}} learning modules from the content library provided below, delimited by ###, for the skill {{skill_name}} targeted in the '{{industry}}' industry."
        persona_suffix = f" in the {{industry}} industry"
    else:
        intro          = f"Create a journey consisting of {{length}} learning modules from the content library provided below, delimited by ###, for the skill {{skill_name}}."
        persona_suffix = ""

    full_template = intro + "\n" + base_rules
    return full_template.format(
        length=length, skill_name=skill_name,
        designation=designation or "", industry=industry or "",
        persona_suffix=persona_suffix, pl_instruction=pl_instruction,
        json_data=json_data
    )


# ── Helper: parse comma-separated cell values ──────────────────────────────────
def parse_cell(val, valid_map):
    """Splits a cell like 'English, Arabic' and maps each to its API value."""
    if pd.isna(val) or str(val).strip() == "":
        return []
    parts = [p.strip() for p in str(val).split(",")]
    return [valid_map[p] for p in parts if p in valid_map]


# ── Helper: generate blank input template Excel ────────────────────────────────
def generate_template():
    template_data = {
        "Skill Name":               ["Communication Skills", "Data Analysis"],
        "Journey Length":           [5, 8],
        "Designation":              ["Manager", "Analyst"],
        "Industry":                 ["Finance", "Technology"],
        "Target Proficiency Level": ["Intermediate", "Advanced"],
        "Duration Filter":          ["Long 20+ mins, Medium 4-20 mins", "Short 0-4 mins"],
        "Language":                 ["English", "English"],
        "Content Type":             ["Module", "Artefact"],
        "Artefact Type":            ["Video, Article", "Podcast"]
    }
    df_template = pd.DataFrame(template_data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_template.to_excel(writer, index=False, sheet_name='Bulk Input')
        workbook   = writer.book
        worksheet  = writer.sheets['Bulk Input']
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#4472C4', 'font_color': 'white', 'border': 1})
        note_fmt   = workbook.add_format({'italic': True, 'font_color': '#888888'})
        notes = [
            "Skill or topic name (required)",
            "A number e.g. 5 (required)",
            "Optional",
            "Optional",
            f"Optional. One or more: {', '.join(PL_OPTIONS)}",
            f"Optional. Comma-sep: {', '.join(DURATION_MAP.keys())}",
            f"Optional. Comma-sep: {', '.join(LANGUAGE_MAP.keys())}",
            f"Optional. One of: {', '.join(CONTENT_TYPE_MAP.keys())}",
            f"Optional. Comma-sep: {', '.join(ARTEFACT_MAP.keys())}"
        ]
        for col_num, (col_name, note) in enumerate(zip(df_template.columns, notes)):
            worksheet.write(0, col_num, col_name, header_fmt)
            worksheet.write(3, col_num, note, note_fmt)
            worksheet.set_column(col_num, col_num, max(len(col_name) + 5, 28))
    output.seek(0)
    return output.getvalue()


# ── Helper: process one row from bulk Excel ────────────────────────────────────
def process_bulk_row(row, accessToken):
    skill_name    = str(row.get("Skill Name", "")).strip()
    length        = str(int(row.get("Journey Length", 5)))
    designation   = str(row.get("Designation", "")).strip() or None
    industry      = str(row.get("Industry", "")).strip() or None
    target_pl_raw = str(row.get("Target Proficiency Level", "")).strip()
    target_pl     = [p.strip() for p in target_pl_raw.split(",") if p.strip() in PL_OPTIONS] if target_pl_raw else []

    selected_durations      = parse_cell(row.get("Duration Filter"),  DURATION_MAP)
    selected_languages      = parse_cell(row.get("Language"),         LANGUAGE_MAP)
    selected_content_types  = parse_cell(row.get("Content Type"),     CONTENT_TYPE_MAP)
    selected_artefact_types = parse_cell(row.get("Artefact Type"),    ARTEFACT_MAP)

    if not skill_name:
        return None, "Skill Name is empty — skipped."

    json_data = searchapi(accessToken, skill_name, selected_durations, selected_languages,
                          selected_content_types, selected_artefact_types)
    if not json_data:
        return None, f"Search API failed for '{skill_name}'."

    context_formatted = build_context(
        length=length, skill_name=skill_name, json_data=json_data,
        designation=designation, industry=industry, target_pl=target_pl
    )
    final_jour = get_completion(context_formatted, "Give me the learning journey")
    journey    = json.loads(final_jour)

    if not journey or not journey.get('journey'):
        return None, f"No content found for '{skill_name}'."

    df_journey = pd.DataFrame(journey['journey'])

    # Merge real PL from DB
    search_data = json.loads(json_data)
    pl_lookup   = {str(item['id']): item['proficiency_level'] for item in search_data}
    df_journey['Proficiency Level'] = df_journey['providerContentId'].astype(str).map(pl_lookup).fillna("Not Specified")

    df_journey['duration']        = df_journey['duration'].astype(int)
    df_journey['Duration (mins)'] = df_journey['duration'].apply(lambda x: round(x / 60, 2))
    df_journey['Description']     = df_journey['Description'].apply(
        lambda x: x[:170] + '...' if len(x) > 170 else x
    )

    # Add identifying columns at the front
    df_journey.insert(0, 'Skill Name',  skill_name)
    df_journey.insert(1, 'Designation', designation or "")
    df_journey.insert(2, 'Industry',    industry or "")

    return df_journey, None


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Login
# ══════════════════════════════════════════════════════════════════════════════
def page1():
    st.title("AI-Powered Learning Journey Curator")
    dbPointer = st.text_input("Enter the DbPointer:", value=st.session_state.dbPointer)
    username  = st.text_input("Enter the UserName:",  value=st.session_state.username)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Single Journey →", use_container_width=True):
            url      = f"https://disprzexternalapi.disprz.com/api/user-authentication/clients/{dbPointer}/users/by-username/{username}"
            headers  = {'Content-Type': 'application/json', 'API-ACCESS-KEY': '36yyyty0Cg3vsodwEv3ecg=='}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                st.session_state.username    = username
                st.session_state.dbPointer   = dbPointer
                st.session_state.accessToken = response.json()['accessToken']
                go_to_page2()
            else:
                st.error('Invalid Username or DbPointer, Please try again', icon="🚨")
    with col2:
        if st.button("📦 Bulk Import / Export →", use_container_width=True):
            url      = f"https://disprzexternalapi.disprz.com/api/user-authentication/clients/{dbPointer}/users/by-username/{username}"
            headers  = {'Content-Type': 'application/json', 'API-ACCESS-KEY': '36yyyty0Cg3vsodwEv3ecg=='}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                st.session_state.username    = username
                st.session_state.dbPointer   = dbPointer
                st.session_state.accessToken = response.json()['accessToken']
                go_to_page3()
            else:
                st.error('Invalid Username or DbPointer, Please try again', icon="🚨")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — Single Journey
# ══════════════════════════════════════════════════════════════════════════════
def page2():
    st.title('AI-Powered Learning Journey Curator')
    if st.button("← Back"):
        go_to_page1()

    if 'form_data'        not in st.session_state: st.session_state.form_data        = None
    if 'final_jour_dict'  not in st.session_state: st.session_state.final_jour_dict  = None
    if 'access_token'     not in st.session_state: st.session_state.access_token     = None
    if 'excel_file'       not in st.session_state: st.session_state.excel_file       = None
    if 'skill_name_state' not in st.session_state: st.session_state.skill_name_state = ""

    with st.form(key='query_form'):
        st.subheader("Learning Journey Details")
        skill_name = st.text_input("Skill Name / Topic Name", "")
        length     = st.number_input("Length of Learning Journeys", min_value=1)

        duration      = st.multiselect("Duration of each item (mins)", options=list(DURATION_MAP.keys()))
        content_type  = st.multiselect("Content Type",                  options=list(CONTENT_TYPE_MAP.keys()))
        language      = st.multiselect("Language",                      options=list(LANGUAGE_MAP.keys()))
        artefact_type = st.multiselect("Artefact Type",                 options=list(ARTEFACT_MAP.keys()))
        target_pl     = st.multiselect(
            "Target Proficiency Level (optional — leave blank to show all)",
            options=PL_OPTIONS
        )
        designation = st.text_input("Designation")
        industry    = st.text_input("Industry")

        submit_button = st.form_submit_button(label='Submit')

        if submit_button:
            selected_durations      = [DURATION_MAP[o]     for o in duration]
            selected_content_types  = [CONTENT_TYPE_MAP[o] for o in content_type]
            selected_languages      = [LANGUAGE_MAP[o]     for o in language]
            selected_artefact_types = [ARTEFACT_MAP[o]     for o in artefact_type]
            st.session_state.skill_name_state = skill_name

            json_data = searchapi(st.session_state.accessToken, skill_name,
                                  selected_durations, selected_languages,
                                  selected_content_types, selected_artefact_types)

            context_formatted = build_context(
                length=str(length), skill_name=skill_name, json_data=json_data,
                designation=designation if designation else None,
                industry=industry if industry else None,
                target_pl=target_pl
            )

            final_jour = get_completion(context_formatted, "Give me the learning journey")
            print(final_jour)
            journey = json.loads(final_jour)

            if journey:
                st.session_state.final_jour_dict = journey['journey']
                df = pd.DataFrame(st.session_state.final_jour_dict)

                if len(df) == 0:
                    st.write("There is no content available with the given requirements")
                else:
                    # Merge real PL from DB
                    search_data = json.loads(json_data)
                    pl_lookup   = {str(item['id']): item['proficiency_level'] for item in search_data}
                    df['Proficiency Level'] = df['providerContentId'].astype(str).map(pl_lookup).fillna("Not Specified")

                    df['duration']        = df['duration'].astype(int)
                    df['Duration (mins)'] = df['duration'].apply(lambda x: round(x / 60, 2))
                    df['Description']     = df['Description'].apply(
                        lambda x: x[:170] + '...' if len(x) > 170 else x
                    )
                    total_minutes = df['Duration (mins)'].sum()
                    hours, minutes = divmod(total_minutes, 60)

                    if target_pl:
                        st.info(f"🎯 Target Proficiency Level: **{', '.join(target_pl)}**")
                    else:
                        pl_summary = ", ".join([f"{pl} ({cnt})" for pl, cnt in df['Proficiency Level'].value_counts().items()])
                        st.info(f"📊 Proficiency levels from DB: **{pl_summary}**")

                    st.write(
                        f"Your Learning Journey consists of **{len(df)}** items and the total learning duration is "
                        f"**{int(hours)} hours and {int(minutes)} minutes**."
                    )
                    st.dataframe(df[['providerContentId', 'Title', 'Description', 'Duration (mins)', 'Proficiency Level', 'reason']])

                    excel_file = BytesIO()
                    export_df  = df[['providerContentId', 'Title', 'Description', 'Duration (mins)', 'Proficiency Level', 'content_type', 'reason']].copy()
                    with pd.ExcelWriter(excel_file, engine='xlsxwriter') as writer:
                        export_df.to_excel(writer, index=False, sheet_name='Learning Journey')
                        ws = writer.sheets['Learning Journey']
                        for i, col in enumerate(export_df.columns):
                            max_len = max(export_df[col].astype(str).map(len).max(), len(col)) + 2
                            ws.set_column(i, i, min(max_len, 60))
                    excel_file.seek(0)
                    st.session_state.excel_file = excel_file.getvalue()
            else:
                st.error('Internal error occurred', icon="🚨")

    if st.session_state.excel_file:
        st.download_button(
            label="📥 Download as Excel",
            data=st.session_state.excel_file,
            file_name="LearningJourneyData.xlsx",
            mime="application/vnd.ms-excel"
        )
    else:
        st.warning("No file available to download.")

    with st.form(key='publish_form'):
        st.subheader("Publish")
        journey_name         = st.text_input("Journey Name", "")
        generate_description = st.form_submit_button(label='Generate Journey Description')

        if generate_description:
            skill_name_for_desc = st.session_state.get('skill_name_state', 'the topic')
            context = (
                f'The learning journey suggested by GPT for the topic - "{skill_name_for_desc}" '
                f'is provided below delimited by ###. Provide a description in about 50-65 words for the users '
                f'to understand about the learning journey before they start learning it. '
                f'The output should be in this format - [{{"description": description}}]. '
                f'Do not return any additional text. ### {st.session_state.final_jour_dict} ###'
            )
            response      = get_completion_desc(context, "Provide the description")
            response_list = json.loads(response)
            st.session_state['journey_desc'] = response_list[0]['description']
            st.text_area("Journey Description", st.session_state['journey_desc'], height=150)

        publish_button = st.form_submit_button(label='Publish as Journey')
        if publish_button:
            if st.session_state.access_token is None:
                st.error("Access Token is not available. Please submit the form first.")
            else:
                request_data = {
                    "accessToken":   st.session_state.access_token,
                    "Journey_Name":  journey_name,
                    "contentIdList": [item['providerContentId'] for item in st.session_state.final_jour_dict]
                }
                publish_response = requests.post(
                    'https://searchservice-msvc-india.disprz.com/v1/trainer-search/learning-items/publish',
                    json=request_data
                )
                if publish_response.status_code == 200:
                    st.success(f"Learning Journey {publish_response.json()['message']}")
                else:
                    st.error(f"Error: {publish_response.text}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — Bulk Import / Export
# ══════════════════════════════════════════════════════════════════════════════
def page3():
    st.title("📦 Bulk Learning Journey Import & Export")
    if st.button("← Back"):
        go_to_page1()

    st.markdown("---")

    # ── Step 1: Download Template ──────────────────────────────────────────────
    st.subheader("Step 1 — Download Input Template")
    st.write("Download the Excel template, fill in your journey requests (one row = one journey), then upload below.")
    st.download_button(
        label="📄 Download Excel Template",
        data=generate_template(),
        file_name="Bulk_Journey_Template.xlsx",
        mime="application/vnd.ms-excel"
    )

    guide_data = {
        "Column":          ["Skill Name", "Journey Length", "Designation", "Industry",
                            "Target Proficiency Level", "Duration Filter", "Language",
                            "Content Type", "Artefact Type"],
        "Required?":       ["✅ Yes", "✅ Yes", "Optional", "Optional",
                            "Optional", "Optional", "Optional", "Optional", "Optional"],
        "Allowed Values":  [
            "Any skill or topic name",
            "A number e.g. 5",
            "Any designation",
            "Any industry",
            f"Comma-sep from: {', '.join(PL_OPTIONS)}",
            f"Comma-sep from: {', '.join(DURATION_MAP.keys())}",
            f"Comma-sep from: {', '.join(LANGUAGE_MAP.keys())}",
            f"One of: {', '.join(CONTENT_TYPE_MAP.keys())}",
            f"Comma-sep from: {', '.join(ARTEFACT_MAP.keys())}"
        ]
    }
    st.dataframe(pd.DataFrame(guide_data), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Step 2: Upload & Process ───────────────────────────────────────────────
    st.subheader("Step 2 — Upload Your Filled Excel & Process")
    uploaded_file = st.file_uploader("Upload your filled Excel file", type=["xlsx"])

    if uploaded_file:
        try:
            input_df = pd.read_excel(uploaded_file)
        except Exception as e:
            st.error(f"Could not read Excel file: {e}")
            return

        st.success(f"✅ File uploaded — **{len(input_df)} journey request(s)** detected.")
        st.dataframe(input_df, use_container_width=True)

        if st.button("🚀 Start Bulk Processing"):
            all_results = []
            failed_rows = []
            total_rows  = len(input_df)
            progress_bar = st.progress(0)
            status_text  = st.empty()

            for idx, row in input_df.iterrows():
                skill = str(row.get("Skill Name", "")).strip() or f"Row {idx + 1}"
                status_text.info(f"⏳ Processing **{idx + 1} of {total_rows}**: {skill}")

                try:
                    df_result, error = process_bulk_row(row, st.session_state.accessToken)
                    if error:
                        failed_rows.append({"Row": idx + 1, "Skill Name": skill, "Reason": error})
                        st.warning(f"⚠️ Row {idx + 1} ({skill}): {error}")
                    else:
                        all_results.append(df_result)
                        st.success(f"✅ Row {idx + 1} ({skill}): **{len(df_result)} items** found")
                except Exception as e:
                    failed_rows.append({"Row": idx + 1, "Skill Name": skill, "Reason": str(e)})
                    st.error(f"❌ Row {idx + 1} ({skill}) failed: {e}")

                progress_bar.progress((idx + 1) / total_rows)

            status_text.success("🎉 Bulk processing complete!")

            # ── Build combined output Excel ────────────────────────────────────
            if all_results:
                combined_df = pd.concat(all_results, ignore_index=True)
                output_cols = ['Skill Name', 'Designation', 'Industry', 'providerContentId',
                               'Title', 'Description', 'Duration (mins)', 'Proficiency Level',
                               'content_type', 'reason']
                combined_df = combined_df[[c for c in output_cols if c in combined_df.columns]]

                st.markdown("---")
                st.subheader("📊 Combined Output Preview")
                st.write(f"**{len(combined_df)} total items** across **{len(all_results)} journeys**")
                st.dataframe(combined_df, use_container_width=True)

                bulk_excel = BytesIO()
                with pd.ExcelWriter(bulk_excel, engine='xlsxwriter') as writer:
                    workbook   = writer.book
                    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#4472C4', 'font_color': 'white', 'border': 1})
                    wrap_fmt   = workbook.add_format({'text_wrap': True, 'valign': 'top'})

                    # Sheet 1: All Journeys combined
                    combined_df.to_excel(writer, index=False, sheet_name='All Journeys')
                    ws_all = writer.sheets['All Journeys']
                    for col_num, col_name in enumerate(combined_df.columns):
                        ws_all.write(0, col_num, col_name, header_fmt)
                        max_len = max(combined_df[col_name].astype(str).map(len).max(), len(col_name)) + 2
                        ws_all.set_column(col_num, col_num, min(max_len, 55), wrap_fmt)

                    # Sheet 2: Summary (one row per journey)
                    summary_rows = []
                    for df_j in all_results:
                        total_mins = df_j['Duration (mins)'].sum()
                        h, m       = divmod(total_mins, 60)
                        pl_counts  = df_j['Proficiency Level'].value_counts().to_dict()
                        summary_rows.append({
                            "Skill Name":         df_j['Skill Name'].iloc[0],
                            "Designation":        df_j['Designation'].iloc[0],
                            "Industry":           df_j['Industry'].iloc[0],
                            "Total Items":        len(df_j),
                            "Total Duration":     f"{int(h)}h {int(m)}m",
                            "Proficiency Levels": ", ".join([f"{k} ({v})" for k, v in pl_counts.items()])
                        })
                    summary_df = pd.DataFrame(summary_rows)
                    summary_df.to_excel(writer, index=False, sheet_name='Summary')
                    ws_sum = writer.sheets['Summary']
                    for col_num, col_name in enumerate(summary_df.columns):
                        ws_sum.write(0, col_num, col_name, header_fmt)
                        ws_sum.set_column(col_num, col_num, max(len(col_name) + 5, 22))

                    # Sheet 3: Failed Rows (only if any)
                    if failed_rows:
                        pd.DataFrame(failed_rows).to_excel(writer, index=False, sheet_name='Failed Rows')

                bulk_excel.seek(0)
                st.download_button(
                    label="📥 Download Bulk Output Excel",
                    data=bulk_excel.getvalue(),
                    file_name="Bulk_Journey_Output.xlsx",
                    mime="application/vnd.ms-excel"
                )

                if failed_rows:
                    st.warning(f"⚠️ {len(failed_rows)} row(s) failed. See 'Failed Rows' sheet in the downloaded Excel.")
            else:
                st.error("❌ No journeys were successfully generated. Please check your input file.")


# ── Router ─────────────────────────────────────────────────────────────────────
if st.session_state.page == 'page1':
    page1()
elif st.session_state.page == 'page2':
    page2()
else:
    page3()