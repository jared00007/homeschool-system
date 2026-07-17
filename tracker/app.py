"""
Compass — a homeschool curriculum platform that blends a Passion Track
(interest-led projects) with a Foundations Track (life skills + financial
literacy) into one parent-controlled weekly plan, on top of the original
schedule, hour-logging-with-parent-approval, grading, and WA compliance base.

Run with:  streamlit run app.py
Data lives in homeschool.db next to this file (or Postgres via DATABASE_URL).

Modes:
  - Student (default): sees today's agenda + links, marks blocks complete
    (creates PENDING entries), views own grades.
  - Parent (localhost only): approves/adjusts/rejects pending hours, grades
    work, sees compliance dashboards, manages assessments, exports records.
"""

from html import escape as escape_html
import os
import random
import re
import sqlite3
import calendar as cal
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit.components.v1 as components
import plotly.graph_objects as go
import streamlit as st

# Two different launch paths import this module differently:
# - Locally (start-tracker.command: `cd tracker/ && streamlit run app.py`)
#   this file runs as the main script, so its own directory is on sys.path
#   and "db_backend" (same-directory) is importable directly.
# - On Streamlit Cloud, the repo-root app.py shim does
#   `sys.path.insert(0, repo_root); from tracker.app import *`, which
#   imports this file as the *submodule* tracker.app — its own directory is
#   NOT auto-added to sys.path in that case, only the repo root is, so it
#   needs the package-qualified "tracker.db_backend" instead.
try:
    from db_backend import connect_database, table_columns, table_exists
except ImportError:
    from tracker.db_backend import connect_database, table_columns, table_exists

DB_PATH = Path(__file__).parent / "homeschool.db"
UPLOADS_BASE = Path(__file__).parent / "uploads"

# Cloud deployment support: if DATABASE_URL or SUPABASE_DB_URL is present,
# the app will use that instead of the local SQLite file.
DB_BACKEND = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
DB_PATH = Path(__file__).parent / "homeschool.db"
if DB_BACKEND:
    DB_PATH = None

# ------------------------------------------------------------- constants
# Product identity (working name — swap freely per the strategy doc).
APP_NAME = "Compass"
APP_TAGLINE = "A curriculum that follows the kid, not the textbook"

WA_SUBJECTS = [
    "Occupational Education", "Science", "Mathematics",
    "Language (Reading/Writing/Spelling)", "Social Studies", "History",
    "Health", "Reading", "Writing", "Spelling", "Art & Music Appreciation",
]

# Foundations Track pillars (the doc's mandatory life-skills half). Each
# foundations_modules row is tagged to one of these.
FOUNDATIONS_PILLARS = [
    "Financial Literacy", "Digital Literacy", "Career Readiness",
    "Health & Wellness", "Life Skills", "Civics",
]

REQUIRED_HOURS = 1000
REQUIRED_DAYS = 180

WA_ASSESSMENT_LAW = (
    "**RCW 28A.200.010** requires one of two things every year: (1) a "
    "standardized achievement test approved by the State Board of Education, "
    "administered by a qualified individual, or (2) a written assessment of "
    "academic progress by a certificated person currently working in "
    "education. Keep the result in his permanent records — it does **not** "
    "get sent to the district. If it shows he isn't making reasonable "
    "progress for his age/stage, you're required to make a good-faith "
    "effort to fix the gap. Non-compliance is treated as truancy under "
    "state law. (Home-based students are explicitly exempt from state "
    "learning standards and public-school standardized tests — this is a "
    "separate, lighter requirement.)"
)

WA_ASSESSMENT_RESOURCES = (
    "**Option A — Standardized test**\n"
    "- [BJU Press Testing](https://www.bjupresstesting.com/) — order a test "
    "kit or find a testing date; results mailed back.\n"
    "- [Seton Testing Services](https://www.setontesting.com/) — similar "
    "process, another common provider homeschoolers use.\n"
    "- Common tests these services offer: **Iowa Test of Basic Skills "
    "(ITBS)**, **Stanford Achievement Test**, **CAT/5** — any of these "
    "satisfies the law, no specific test is required.\n"
    "- Many WA homeschool co-ops also run a group testing day each spring "
    "— cheaper and social. Ask around before booking one of the above.\n\n"
    "**Option B — Written evaluation by a certificated person**\n"
    "- Ask a co-op, tutor, or a friend who currently holds a WA teaching "
    "certificate to review a work sample and write a short letter of "
    "satisfactory progress. Often free or cheaper than a test.\n"
    "- The Export tab's CSVs (hours, grades, assessments) give an evaluator "
    "something concrete to look at instead of starting from nothing.\n\n"
    "**Washington-specific help**\n"
    "- [Washington Homeschool Organization](https://washhomeschool.org/) — "
    "statewide homeschool group; their "
    "[testing overview](https://washhomeschool.org/all-about-testing-part-1/) "
    "walks through the same two options in more depth.\n"
    "- OSPI Learning Options Department (cited by the [State Board of "
    "Education FAQ](https://sbe.wa.gov/faqs/211)) for anything test/"
    "evaluator-specific the law doesn't spell out: **360-725-6233**, "
    "**homebased@k12.wa.us**.\n\n"
    "Pick a route now, log the plan in this tab, then come back and fill "
    "in the actual result once it's done."
)

CURRICULUM_RESOURCES = {
    "Mathematics": ("Khan Academy — 8th Grade Math",
                    "https://www.khanacademy.org/math/cc-eighth-grade-math",
                    "Work through units in order; use the mastery system.",
                    ["Go to the link and log in with your school email.",
                     "Click \"Course,\" and make sure \"8th grade\" is selected.",
                     "Find the first unit that isn't fully mastered yet — look "
                     "for a progress bar that isn't 100% filled in.",
                     "Work through that unit's lessons in order: watch the "
                     "instructional video first, then do the practice problems.",
                     "Finish at least one full lesson OR 20 practice problems "
                     "this block, whichever comes first.",
                     "Missed a problem? Read the hint or \"explain\" article "
                     "before trying again — don't just guess.",
                     "When the block is over, click \"✅ Done, got it\" below — "
                     "or \"😕 Done, still fuzzy\" if it didn't quite click."]),
    "Mathematics — IXL": ("IXL Math — 8th Grade",
                          "https://www.ixl.com/math/grade-8",
                          "Dedicated IXL practice time — separate from the main "
                          "Khan Academy block, targets specific skill gaps.",
                          ["Go to the link and log in with your IXL account.",
                           "If a parent assigned specific skills, do those first "
                           "— check for a \"Recommendations\" or assigned list.",
                           "If nothing's assigned, work on whichever skill has "
                           "the lowest score (IXL shows a score per skill, aim "
                           "to bring it above 80).",
                           "Keep going until the block ends — don't stop after "
                           "just one or two questions.",
                           "When the block is over, click \"✅ Done, got it\" "
                           "below — or \"😕 Done, still fuzzy\" if it didn't "
                           "quite click."]),
    "Reading": ("CommonLit / library book",
                "https://www.commonlit.org/",
                "Passage + questions, or independent reading. Supplement 2x/week "
                "with Vocabulary.com (vocabulary.com) — matches the Vocabulary "
                "section on standardized tests like ITBS/Stanford.",
                ["If using CommonLit: log in, open the next assigned passage "
                 "(or pick one at your grade level if nothing's assigned), and "
                 "read the whole thing before answering anything.",
                 "Answer every question at the end of the passage — don't skip any.",
                 "If reading a library book instead: read for the entire block "
                 "and keep track of what page you stopped on.",
                 "Twice a week, spend this block on Vocabulary.com instead of "
                 "a passage/book — ask a parent which days.",
                 "Click \"✅ Done, got it\" below when the block is finished — "
                 "or \"😕 Done, still fuzzy\" if it didn't quite click."]),
    "Writing": ("ReadWorks prompts + journal",
                "https://www.readworks.org/",
                "One structured piece weekly; parent reviews. Supplement 2x/week "
                "with Khan Academy Grammar (same Khan login) for capitalization, "
                "punctuation & usage — the \"Language Mechanics\" section on "
                "standardized tests.",
                ["Go to ReadWorks and find this week's writing prompt (reuse "
                 "last week's if nothing new is assigned).",
                 "Spend the first 5 minutes planning: write down 3-4 points "
                 "you want to make before you start the actual writing.",
                 "Write a full response — one opening sentence, 2-3 supporting "
                 "points with real detail/examples, one closing sentence.",
                 "Read it back once and fix obvious mistakes before you're done.",
                 "Twice a week, use this block for Khan Academy Grammar "
                 "instead (same login) — ask a parent which days.",
                 "Leave your writing somewhere a parent can see it, then click "
                 "\"✅ Done, got it\" below — or \"😕 Done, still fuzzy\" if "
                 "it didn't quite click."]),
    "Science": ("CK-12 FlexBooks",
                "https://www.ck12.org/student/",
                "Read the chapter, do the adaptive practice.",
                ["Go to the link, log in, and open the current chapter — ask "
                 "a parent if you're not sure which one you're on.",
                 "Read the entire section for today. Don't skim — if a "
                 "sentence doesn't make sense, re-read it before moving on.",
                 "Do the adaptive practice questions at the end of the section.",
                 "If a concept still doesn't make sense after the practice, "
                 "write down the question to ask a parent later.",
                 "Click \"✅ Done, got it\" below when finished — or \"😕 Done, still "
                "fuzzy\" if it didn't quite click."]),
    "Social Studies": ("Khan Academy — Civics/Economics",
                       "https://www.khanacademy.org/economics-finance-domain",
                       "Civics and economics units.",
                       ["Go to the link, log in, and open the Civics or "
                        "Economics unit you're currently working through.",
                        "Watch the lesson video first, then do the practice set.",
                        "Complete at least one full lesson this block.",
                        "Click \"✅ Done, got it\" below when finished — or \"😕 Done, still "
                "fuzzy\" if it didn't quite click."]),
    "History": ("Khan Academy US History + Crash Course",
                "https://www.khanacademy.org/humanities/us-history",
                "Khan for structure; Crash Course as supplement.",
                ["Go to Khan Academy US History, find your current unit, and "
                 "complete one full lesson (video + practice).",
                 "If you finish early, search YouTube for the matching Crash "
                 "Course US History episode on the same topic — good extra context.",
                 "Click \"✅ Done, got it\" below when finished — or \"😕 Done, still "
                "fuzzy\" if it didn't quite click."]),
    "Health": ("CDC BAM! Body & Mind",
               "https://www.cdc.gov/bam/index.html",
               "Short weekly unit — nutrition, first aid, fitness.",
               ["Go to the link and open this week's topic (nutrition, first "
                "aid, or fitness) — ask a parent if nothing's assigned yet.",
                "Read/complete the short unit for that topic.",
                "These units are quick — use any leftover time on an actual "
                "healthy habit (a short walk, planning a healthy meal, etc.) "
                "and jot down what you did.",
                "Click \"✅ Done, got it\" below when finished — or \"😕 Done, still "
                "fuzzy\" if it didn't quite click."]),
    "Art & Music Appreciation": ("Khan Academy Art/Music + museum stops",
                                 "https://www.khanacademy.org/humanities/music",
                                 "Museum visits count — log them as field trips.",
                                 ["Go to the link and complete one lesson in "
                                  "either art or music appreciation.",
                                  "If a museum, gallery, or concert happened this "
                                  "week, that counts instead — tell a parent so "
                                  "they can log it as a field trip.",
                                  "Click \"✅ Done, got it\" below when finished — or \"😕 Done, still "
                "fuzzy\" if it didn't quite click."]),
    "Occupational Education": ("Life skills / careers",
                               "https://www.khanacademy.org/college-careers-more",
                               "Budgeting, careers, or shadowing a parent's work.",
                               ["Go to the link and explore one topic: "
                                "budgeting, a specific career, or general job skills.",
                                "Or, if you're helping/shadowing a parent's work "
                                "task today, that counts instead — jot down what "
                                "you learned.",
                                "Click \"✅ Done, got it\" below when finished — or \"😕 Done, still "
                "fuzzy\" if it didn't quite click."]),
    "Electives": ("Duolingo Spanish / coding",
                  "https://www.duolingo.com/",
                  "Flexible slot — follow his interest.",
                  ["Open whichever elective you've picked (see 🎯 Electives & "
                   "Books for your choices).",
                   "Do one full lesson or session — aim for 15-20 focused minutes.",
                   "Click \"✅ Done, got it\" below when finished — or \"😕 Done, still "
                "fuzzy\" if it didn't quite click."]),
}

MAX_ELECTIVES = 2

# Seed data only — the live, editable pool lives in the elective_pool DB table
# (parents manage it from Parent > Curriculum > Manage elective options).
DEFAULT_ELECTIVE_POOL = {
    "World Language — Spanish": (
        "Duolingo Spanish", "https://www.duolingo.com/",
        "Daily practice; aim for a 15-20 min lesson per session."),
    "Computer Science — Intro to Coding": (
        "Code.org CS Discoveries", "https://code.org/educate/csd",
        "Self-paced units covering web dev, games, and data."),
    "Personal Finance": (
        "Khan Academy Personal Finance",
        "https://www.khanacademy.org/college-careers-more/personal-finance",
        "Budgeting, saving, credit, and taxes basics."),
    "Art — Drawing & Design": (
        "Khan Academy Art & sketchbook practice",
        "https://www.khanacademy.org/humanities/art-history",
        "Weekly sketchbook page + one Khan Academy art lesson."),
    "Music — Instrument Practice": (
        "Practice log + Musictheory.net lessons",
        "https://www.musictheory.net/",
        "Log practice minutes; theory lessons for music reading."),
    "Photography": (
        "Free photography basics course",
        "https://www.photographycourse.net/",
        "Composition, lighting, and a monthly photo project."),
    "Drama & Public Speaking": (
        "Speech/debate prompts + recorded practice",
        "https://www.toastmasters.org/",
        "Prepare and record a short speech every 2 weeks."),
    "Chess": (
        "Chess.com lessons & puzzles",
        "https://www.chess.com/lessons",
        "Puzzles + one studied opening per week."),
    "Woodworking / Shop Skills": (
        "Beginner woodworking project guides",
        "https://www.youtube.com/results?search_query=beginner+woodworking+projects",
        "One small project per month; log time and photos."),
    "Environmental Science / Gardening": (
        "Project-based gardening & ecology unit",
        "https://www.nps.gov/kids/become-a-junior-ranger.htm",
        "Hands-on growing log + a related junior ranger badge."),
}

# Seed data only — the live, editable pool lives in the book_pool DB table
# (parents manage it from Parent > Curriculum > Manage book pool).
DEFAULT_BOOK_POOL = [
    {"title": "The Giver", "author": "Lois Lowry",
     "ties_to": "Reading — dystopian fiction & ethics",
     "link": "https://www.commonlit.org/en/texts/the-giver"},
    {"title": "Number the Stars", "author": "Lois Lowry",
     "ties_to": "History — WWII & the Holocaust",
     "link": "https://www.goodreads.com/book/show/128881.Number_the_Stars"},
    {"title": "Bud, Not Buddy", "author": "Christopher Paul Curtis",
     "ties_to": "History — the Great Depression",
     "link": "https://www.goodreads.com/book/show/107255.Bud_Not_Buddy"},
    {"title": "The Outsiders", "author": "S. E. Hinton",
     "ties_to": "Reading — coming-of-age & social class",
     "link": "https://www.goodreads.com/book/show/659.The_Outsiders"},
    {"title": "A Wrinkle in Time", "author": "Madeleine L'Engle",
     "ties_to": "Science — physics concepts & sci-fi",
     "link": "https://www.goodreads.com/book/show/18131.A_Wrinkle_in_Time"},
    {"title": "Hatchet", "author": "Gary Paulsen",
     "ties_to": "Science — wilderness survival & ecology",
     "link": "https://www.goodreads.com/book/show/58989.Hatchet"},
    {"title": "Chains", "author": "Laurie Halse Anderson",
     "ties_to": "History — American Revolution & slavery",
     "link": "https://www.goodreads.com/book/show/896081.Chains"},
    {"title": "The Watsons Go to Birmingham — 1963", "author": "Christopher Paul Curtis",
     "ties_to": "History — the Civil Rights era",
     "link": "https://www.goodreads.com/book/show/48750.The_Watsons_Go_to_Birmingham_1963"},
    {"title": "Fever 1793", "author": "Laurie Halse Anderson",
     "ties_to": "History/Science — colonial America & epidemics",
     "link": "https://www.goodreads.com/book/show/337213.Fever_1793"},
    {"title": "The Phantom Tollbooth", "author": "Norton Juster",
     "ties_to": "Reading/Math — wordplay & logic",
     "link": "https://www.goodreads.com/book/show/378.The_Phantom_Tollbooth"},
    {"title": "Ender's Game", "author": "Orson Scott Card",
     "ties_to": "Reading — sci-fi & strategy/ethics",
     "link": "https://www.goodreads.com/book/show/375802.Ender_s_Game"},
    {"title": "The Crossover", "author": "Kwame Alexander",
     "ties_to": "Reading — verse novel & family",
     "link": "https://www.goodreads.com/book/show/18263725-the-crossover"},
]

SCOPE_FRAMING_NOTE = (
    "As a WA DOI homeschooler, there are no state-mandated grade-level "
    "standards — the 11 subject areas must be covered, but you decide depth "
    "and pace. What follows is the typical 8th-grade scope (roughly aligned "
    "to what public schools target), worth loosely tracking since it keeps "
    "him on-ramp-ready for 9th grade and Running Start later."
)

# Typical 8th-grade scope by subject — reference only, not tracked/graded.
SCOPE_BY_SUBJECT = {
    "Mathematics": (
        "Pre-algebra completing into Algebra 1 readiness: linear equations "
        "and functions, systems of equations, exponents and scientific "
        "notation, Pythagorean theorem, volume, intro statistics (scatter "
        "plots, two-way tables). If he's strong, many homeschoolers just do "
        "Algebra 1 in 8th — a full year ahead, sets up calculus by senior year."),
    "Reading / Writing (ELA)": (
        "Analyzing literature (theme, character arcs, author's purpose), "
        "argumentative and explanatory essay writing with evidence, research "
        "skills with citations, grammar refinement, vocabulary in context. "
        "Reading list typically mixes classic novels and nonfiction."),
    "Science": (
        "Usually a physical science year: motion and forces, energy, waves, "
        "atoms and the periodic table, chemical reactions — plus some "
        "earth/space (plate tectonics, astronomy)."),
    "Social Studies / History": (
        "Most commonly U.S. history (colonial era through Reconstruction or "
        "Civil War) plus civics: Constitution, branches of government, how "
        "laws work. Washington also expects Pacific Northwest history "
        "somewhere in middle school — worth folding in."),
    "Health": (
        "Nutrition, body systems, mental health basics, first aid, "
        "decision-making around substances."),
    "Occ. Ed / Art & Music / Electives": (
        "Wide open at this age — follow his interest."),
}

# Seed data only — the live, editable pool lives in the fun_project_pool DB
# table (parents manage it from the 🗺️ Quest Board tab).
DEFAULT_FUN_PROJECTS = [
    {"title": "Real Family Budget Challenge", "subject": "Mathematics",
     "description": "Take the family grocery or fuel budget for a week and "
                    "optimize it — real linear equations and percentages "
                    "with actual stakes."},
    {"title": "Sports / Fantasy League Stats", "subject": "Mathematics",
     "description": "Track scatter plots and averages hiding inside a "
                    "fantasy league or sports stats he already follows."},
    {"title": "Spreadsheet Modeling", "subject": "Mathematics",
     "description": "Build a formula-driven spreadsheet — algebra in "
                    "disguise, and a real analytics skill."},
    {"title": "RV Rolling Physics Lab", "subject": "Science",
     "description": "Towing weight distribution, tire pressure vs. "
                    "temperature, battery/solar amp-hours, propane "
                    "consumption — real physical science on the road."},
    {"title": "Kitchen Chemistry", "subject": "Science",
     "description": "Baking as chemical reactions, Mentos/Coke "
                    "stoichiometry-lite, build a water rocket."},
    {"title": "National Park Geology Stops", "subject": "Science",
     "description": "Turn national park visits into plate tectonics and "
                    "geology units — standing at Mount Rainier hits "
                    "different than reading about it."},
    {"title": "Route the RV Through History", "subject": "History",
     "description": "Plan stops at Lewis & Clark sites, Oregon Trail "
                    "landmarks, or Civil War battlefields — reading about "
                    "Gettysburg vs. standing on it are different experiences."},
    {"title": "Junior Ranger Badges", "subject": "History",
     "description": "Junior Ranger programs at national parks — several "
                    "badges are legitimately history/civics coursework."},
    {"title": "Family Constitutional Convention", "subject": "Social Studies",
     "description": "Mock trial or family 'constitutional convention' — "
                    "argue a case for a household rule change using real "
                    "constitutional reasoning."},
    {"title": "Travel Blog or YouTube Script", "subject": "Writing",
     "description": "Swap an essay for a travel blog post or video script — "
                    "same structure/evidence/audience skills, way more "
                    "motivating because it's published."},
    {"title": "Pick Half the Reading List", "subject": "Reading",
     "description": "Let him choose half of what he reads — graphic novels "
                    "and quality nonfiction count."},
    {"title": "Podcast-Style Book Report", "subject": "Reading",
     "description": "Record him arguing why a book was great or terrible, "
                    "podcast-style, instead of a written report."},
    {"title": "Plan a Purposeful Hike", "subject": "Health",
     "description": "He plans the route, calculates distance/elevation/"
                    "water needs — health, math, and occupational ed in "
                    "one trail."},
    {"title": "Cook a Dinner on a Nutrition Target", "subject": "Health",
     "description": "Plan and cook one dinner a week that hits a nutrition "
                    "target he sets."},
    {"title": "Real Dataset, Real Question", "subject": "Occupational Education",
     "description": "Shadow a parent's work with a small real dataset and "
                    "a genuine question to answer."},
    {"title": "Run a Piece of the RV Transition", "subject": "Occupational Education",
     "description": "Own one part of the RV/truck transition project — "
                    "comparing campground costs, tracking the truck search "
                    "— genuine project management."},
]

# Starter Quest Log projects built around Landon's actual interests (games,
# YouTube, comics, Legos) — added incrementally below rather than in the
# COUNT(*)==0 seed block above, since the pool is already populated.
# mess_level kept "Low" throughout, per the parent's cleanup concern.
LANDON_FUN_PROJECT_SEEDS = [
    {"title": "YouTube Short Studio", "subjects": "Writing, Occupational Education",
     "icon": "🎬",
     "description": "Script, film, and edit a short-form video start to finish.",
     "steps": "Pick a topic and write a 1-paragraph idea.\n"
              "Write a short script (what you'll say, in order).\n"
              "Film it — multiple takes are fine.\n"
              "Edit it into one final cut.\n"
              "Watch it back once before calling it done.",
     "mess_level": "Low", "est_hours": 2.0},
    {"title": "Comic Book Studio", "subjects": "Writing, Art & Music Appreciation",
     "icon": "📖",
     "description": "One comic page, done slowly and completely instead of rushed.",
     "steps": "Idea: write one sentence describing the page's story beat.\n"
              "Thumbnail: tiny, rough panel layout sketch — no detail yet.\n"
              "Full pencils: draw the real panels, take your time.\n"
              "Ink: trace your pencils in pen.\n"
              "Color: every panel gets color — no page is done until color is finished.",
     "mess_level": "Low", "est_hours": 2.0},
    {"title": "Lego Math Challenge", "subjects": "Mathematics",
     "icon": "🧱",
     "description": "Use Lego bricks to physically model a math concept "
                    "(area/volume, ratios, fractions via studs).",
     "steps": "Pick a concept (area, volume, ratio, or fractions).\n"
              "Build a physical example with Lego.\n"
              "Write down the math it demonstrates.\n"
              "Explain it out loud to a parent.",
     "mess_level": "Low", "est_hours": 1.0},
    {"title": "Design Your Own Game Level",
     "subjects": "Occupational Education, Art & Music Appreciation",
     "icon": "🎮",
     "description": "Design (on paper or in a free tool) one level/map for a "
                    "game idea — layout, rules, objective.",
     "steps": "Pick the kind of game (platformer, puzzle, etc).\n"
              "Sketch the level layout on paper.\n"
              "Write the rules/objective in your own words.\n"
              "Describe it to a parent like you're pitching it.",
     "mess_level": "Low", "est_hours": 1.5},
]

# Seed data for the national_parks pool — the 63 congressionally-designated
# U.S. National Parks, with state and approximate visitor-center coordinates
# for the map view. Junior Ranger programs exist at nearly every NPS site;
# no per-park link is included since NPS page URLs aren't consistent enough
# to guess reliably (verified: some parks use different slugs entirely) —
# use the general links in the National Parks tab instead.
# NPS's current 12-region structure (DOI Unified Regions), verified against
# nps.gov/aboutus/contactinformation.htm. Region assignment is state-based per
# NPS's own definitions, except: (a) Florida parks are placed in Region 2
# ("South Atlantic - Gulf") even though NPS's summary blurb only lists AL/GA/
# NC/PR/SC/TN — the region's own name and Florida's geography make this the
# clear fit, the state list just reads as incomplete; (b) the California/
# Nevada split between Region 8 ("southern CA/NV") and Region 10 ("middle and
# north CA, most of NV") isn't published per-park by NPS, so that boundary is
# approximated by each park's actual location.
NPS_REGIONS = [
    "North Atlantic-Appalachian", "South Atlantic-Gulf", "Great Lakes",
    "Mississippi Basin", "Missouri Basin", "Rio Grande-Texas Gulf",
    "Upper Colorado Basin", "Lower Colorado Basin",
    "Columbia-Pacific Northwest", "California-Great Basin", "Alaska",
    "Pacific Islands",
]

# Validated dataviz-skill palette (references/palette.md), light mode.
# Slot 1 (blue) is reserved for cities so they never collide with a region hue.
MAP_CITY_COLOR = "#2a78d6"
MAP_STATE_VISITED_COLOR = "#0ca30c"   # status "good"
MAP_STATE_UNVISITED_COLOR = "#e1e0d9"  # gridline/neutral
MAP_REGION_PALETTE = ["#1baf7a", "#eda100", "#008300", "#4a3aa7",
                      "#e34948", "#e87ba4", "#eb6834"]  # slots 2-8
MAP_REGION_MUTED = "#898781"  # overflow beyond 7 distinct regions ("Other")


def get_region_color_map(present_regions):
    """Assign the palette's 7 region hues to whichever NPS regions a family
    actually has visits in, in NPS_REGIONS canonical order — so a family's
    own regions always get a distinct color, regardless of which specific
    ones they are (a fixed assignment would mute out regions that just sort
    late in the list). Overflow beyond 7 distinct regions folds to muted."""
    ordered_present = [r for r in NPS_REGIONS if r in present_regions]
    return {r: (MAP_REGION_PALETTE[i] if i < len(MAP_REGION_PALETTE) else MAP_REGION_MUTED)
            for i, r in enumerate(ordered_present)}

DEFAULT_NATIONAL_PARKS = [
    # name, state, lat, lon, region
    ("Acadia", "Maine", 44.35, -68.21, "North Atlantic-Appalachian"),
    ("American Samoa", "American Samoa", -14.25, -170.68, "Pacific Islands"),
    ("Arches", "Utah", 38.73, -109.59, "Upper Colorado Basin"),
    ("Badlands", "South Dakota", 43.75, -102.50, "Missouri Basin"),
    ("Big Bend", "Texas", 29.25, -103.25, "Rio Grande-Texas Gulf"),
    ("Biscayne", "Florida", 25.65, -80.20, "South Atlantic-Gulf"),
    ("Black Canyon of the Gunnison", "Colorado", 38.57, -107.72, "Upper Colorado Basin"),
    ("Bryce Canyon", "Utah", 37.59, -112.19, "Upper Colorado Basin"),
    ("Canyonlands", "Utah", 38.20, -109.93, "Upper Colorado Basin"),
    ("Capitol Reef", "Utah", 38.20, -111.17, "Upper Colorado Basin"),
    ("Carlsbad Caverns", "New Mexico", 32.17, -104.44, "Upper Colorado Basin"),
    ("Channel Islands", "California", 34.01, -119.42, "Lower Colorado Basin"),
    ("Congaree", "South Carolina", 33.78, -80.78, "South Atlantic-Gulf"),
    ("Crater Lake", "Oregon", 42.94, -122.10, "Columbia-Pacific Northwest"),
    ("Cuyahoga Valley", "Ohio", 41.24, -81.55, "Great Lakes"),
    ("Death Valley", "California/Nevada", 36.50, -117.08, "Lower Colorado Basin"),
    ("Denali", "Alaska", 63.33, -150.50, "Alaska"),
    ("Dry Tortugas", "Florida", 24.63, -82.87, "South Atlantic-Gulf"),
    ("Everglades", "Florida", 25.29, -80.90, "South Atlantic-Gulf"),
    ("Gates of the Arctic", "Alaska", 67.78, -153.30, "Alaska"),
    ("Gateway Arch", "Missouri", 38.63, -90.19, "Mississippi Basin"),
    ("Glacier", "Montana", 48.70, -113.72, "Missouri Basin"),
    ("Glacier Bay", "Alaska", 58.50, -137.00, "Alaska"),
    ("Grand Canyon", "Arizona", 36.06, -112.14, "Lower Colorado Basin"),
    ("Grand Teton", "Wyoming", 43.79, -110.68, "Upper Colorado Basin"),
    ("Great Basin", "Nevada", 39.00, -114.22, "California-Great Basin"),
    ("Great Sand Dunes", "Colorado", 37.79, -105.59, "Upper Colorado Basin"),
    ("Great Smoky Mountains", "Tennessee/North Carolina", 35.68, -83.53, "South Atlantic-Gulf"),
    ("Guadalupe Mountains", "Texas", 31.92, -104.87, "Rio Grande-Texas Gulf"),
    ("Haleakalā", "Hawaii", 20.72, -156.17, "Pacific Islands"),
    ("Hawaiʻi Volcanoes", "Hawaii", 19.38, -155.20, "Pacific Islands"),
    ("Hot Springs", "Arkansas", 34.51, -93.05, "Mississippi Basin"),
    ("Indiana Dunes", "Indiana", 41.65, -87.05, "Great Lakes"),
    ("Isle Royale", "Michigan", 48.10, -88.55, "Great Lakes"),
    ("Joshua Tree", "California", 33.87, -115.90, "Lower Colorado Basin"),
    ("Katmai", "Alaska", 58.50, -155.00, "Alaska"),
    ("Kenai Fjords", "Alaska", 59.92, -149.65, "Alaska"),
    ("Kings Canyon", "California", 36.80, -118.55, "California-Great Basin"),
    ("Kobuk Valley", "Alaska", 67.55, -159.28, "Alaska"),
    ("Lake Clark", "Alaska", 60.97, -153.42, "Alaska"),
    ("Lassen Volcanic", "California", 40.49, -121.42, "California-Great Basin"),
    ("Mammoth Cave", "Kentucky", 37.19, -86.10, "North Atlantic-Appalachian"),
    ("Mesa Verde", "Colorado", 37.18, -108.49, "Upper Colorado Basin"),
    ("Mount Rainier", "Washington", 46.85, -121.76, "Columbia-Pacific Northwest"),
    ("New River Gorge", "West Virginia", 38.07, -81.08, "North Atlantic-Appalachian"),
    ("North Cascades", "Washington", 48.70, -121.20, "Columbia-Pacific Northwest"),
    ("Olympic", "Washington", 47.80, -123.60, "Columbia-Pacific Northwest"),
    ("Petrified Forest", "Arizona", 35.07, -109.78, "Lower Colorado Basin"),
    ("Pinnacles", "California", 36.48, -121.16, "California-Great Basin"),
    ("Redwood", "California", 41.21, -124.00, "California-Great Basin"),
    ("Rocky Mountain", "Colorado", 40.34, -105.68, "Upper Colorado Basin"),
    ("Saguaro", "Arizona", 32.25, -110.50, "Lower Colorado Basin"),
    ("Sequoia", "California", 36.49, -118.57, "California-Great Basin"),
    ("Shenandoah", "Virginia", 38.53, -78.35, "North Atlantic-Appalachian"),
    ("Theodore Roosevelt", "North Dakota", 46.97, -103.45, "Missouri Basin"),
    ("Virgin Islands", "U.S. Virgin Islands", 18.33, -64.73, "South Atlantic-Gulf"),
    ("Voyageurs", "Minnesota", 48.50, -92.88, "Great Lakes"),
    ("White Sands", "New Mexico", 32.78, -106.17, "Upper Colorado Basin"),
    ("Wind Cave", "South Dakota", 43.57, -103.48, "Missouri Basin"),
    ("Wrangell-St. Elias", "Alaska", 61.71, -142.99, "Alaska"),
    ("Yellowstone", "Wyoming/Montana/Idaho", 44.60, -110.55, "Upper Colorado Basin"),
    ("Yosemite", "California", 37.87, -119.54, "California-Great Basin"),
    ("Zion", "Utah", 37.30, -113.05, "Upper Colorado Basin"),
]

NPS_JUNIOR_RANGER_LINKS = (
    "https://www.nps.gov/kids/become-a-junior-ranger.htm",
    "https://www.nps.gov/kids/parks-with-junior-ranger-programs.htm",
)

# name -> 2-letter postal code, for the choropleth map (all 50 + DC).
US_STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "District of Columbia": "DC",
}
US_STATES = list(US_STATE_ABBR.keys())

# Seed data for the major_cities pool: every state capital + DC, plus a
# handful of other major population centers worth tracking on the map.
DEFAULT_MAJOR_CITIES = [
    ("Montgomery", "Alabama", 32.3792, -86.3077),
    ("Juneau", "Alaska", 58.3019, -134.4197),
    ("Phoenix", "Arizona", 33.4484, -112.0740),
    ("Little Rock", "Arkansas", 34.7465, -92.2896),
    ("Sacramento", "California", 38.5816, -121.4944),
    ("Denver", "Colorado", 39.7392, -104.9903),
    ("Hartford", "Connecticut", 41.7658, -72.6734),
    ("Dover", "Delaware", 39.1582, -75.5244),
    ("Tallahassee", "Florida", 30.4383, -84.2807),
    ("Atlanta", "Georgia", 33.7490, -84.3880),
    ("Honolulu", "Hawaii", 21.3069, -157.8583),
    ("Boise", "Idaho", 43.6150, -116.2023),
    ("Springfield", "Illinois", 39.7817, -89.6501),
    ("Indianapolis", "Indiana", 39.7684, -86.1581),
    ("Des Moines", "Iowa", 41.5868, -93.6250),
    ("Topeka", "Kansas", 39.0473, -95.6752),
    ("Frankfort", "Kentucky", 38.2009, -84.8733),
    ("Baton Rouge", "Louisiana", 30.4515, -91.1871),
    ("Augusta", "Maine", 44.3106, -69.7795),
    ("Annapolis", "Maryland", 38.9784, -76.4922),
    ("Boston", "Massachusetts", 42.3601, -71.0589),
    ("Lansing", "Michigan", 42.7325, -84.5555),
    ("Saint Paul", "Minnesota", 44.9537, -93.0900),
    ("Jackson", "Mississippi", 32.2988, -90.1848),
    ("Jefferson City", "Missouri", 38.5767, -92.1735),
    ("Helena", "Montana", 46.5891, -112.0391),
    ("Lincoln", "Nebraska", 40.8136, -96.7026),
    ("Carson City", "Nevada", 39.1638, -119.7674),
    ("Concord", "New Hampshire", 43.2081, -71.5376),
    ("Trenton", "New Jersey", 40.2206, -74.7597),
    ("Santa Fe", "New Mexico", 35.6870, -105.9378),
    ("Albany", "New York", 42.6526, -73.7562),
    ("Raleigh", "North Carolina", 35.7796, -78.6382),
    ("Bismarck", "North Dakota", 46.8083, -100.7837),
    ("Columbus", "Ohio", 39.9612, -82.9988),
    ("Oklahoma City", "Oklahoma", 35.4676, -97.5164),
    ("Salem", "Oregon", 44.9429, -123.0351),
    ("Harrisburg", "Pennsylvania", 40.2732, -76.8867),
    ("Providence", "Rhode Island", 41.8240, -71.4128),
    ("Columbia", "South Carolina", 34.0007, -81.0348),
    ("Pierre", "South Dakota", 44.3683, -100.3510),
    ("Nashville", "Tennessee", 36.1627, -86.7816),
    ("Austin", "Texas", 30.2672, -97.7431),
    ("Salt Lake City", "Utah", 40.7608, -111.8910),
    ("Montpelier", "Vermont", 44.2601, -72.5754),
    ("Richmond", "Virginia", 37.5407, -77.4360),
    ("Olympia", "Washington", 47.0379, -122.9007),
    ("Charleston", "West Virginia", 38.3498, -81.6326),
    ("Madison", "Wisconsin", 43.0731, -89.4012),
    ("Cheyenne", "Wyoming", 41.1400, -104.8202),
    ("Washington", "District of Columbia", 38.9072, -77.0369),
    ("New York City", "New York", 40.7128, -74.0060),
    ("Los Angeles", "California", 34.0522, -118.2437),
    ("Chicago", "Illinois", 41.8781, -87.6298),
    ("Houston", "Texas", 29.7604, -95.3698),
    ("Philadelphia", "Pennsylvania", 39.9526, -75.1652),
    ("San Antonio", "Texas", 29.4241, -98.4936),
    ("San Diego", "California", 32.7157, -117.1611),
    ("Dallas", "Texas", 32.7767, -96.7970),
    ("San Jose", "California", 37.3382, -121.8863),
    ("Seattle", "Washington", 47.6062, -122.3321),
    ("Las Vegas", "Nevada", 36.1699, -115.1398),
    ("Portland", "Oregon", 45.5152, -122.6784),
    ("Miami", "Florida", 25.7617, -80.1918),
    ("San Francisco", "California", 37.7749, -122.4194),
    ("Detroit", "Michigan", 42.3314, -83.0458),
    ("Memphis", "Tennessee", 35.1495, -90.0490),
    ("Milwaukee", "Wisconsin", 43.0389, -87.9065),
    ("Charlotte", "North Carolina", 35.2271, -80.8431),
    ("El Paso", "Texas", 31.7619, -106.4850),
    ("Spokane", "Washington", 47.6588, -117.4260),
]

# Smithsonian Learning Lab collections — free, no login needed to browse, and
# all Smithsonian-created and filtered to the middle-school (13-15) age band,
# which is Landon's. Deliberately specific collections rather than a saved
# search URL: search links carry filter params that rot, whereas a collection
# URL keeps working. Seeded into curriculum_materials as links, so they show up
# in the Resources tab like any other material a parent adds. Browse for more
# at: https://learninglab.si.edu/search/?st=&f[_types][]=ll_collection
SMITHSONIAN_LEARNING_LAB_SEEDS = [
    {"title": "Smithsonian: Exploring Identity through Portraiture",
     "subject": "Art & Music Appreciation",
     "url": "https://learninglab.si.edu/collections/exploring-identity-through-portraiture/AfsekHKtni1NAfE6",
     "notes": "National Portrait Gallery — how artists show who someone is. "
              "Good jumping-off point for character design."},
    {"title": "Smithsonian: Creating Portraits of Community",
     "subject": "Art & Music Appreciation",
     "url": "https://learninglab.si.edu/collections/creating-portraits-of-community/RVD97As4BrMxSv3P",
     "notes": "National Portrait Gallery — make a portrait of the people and "
              "places around you."},
    {"title": "Smithsonian: Digital Storytelling",
     "subject": "Writing",
     "url": "https://learninglab.si.edu/collections/digital-storytelling-for-classroom-engagement-companion-collection-for-a-smithsonian-national-education-summit-presentation/QndpD0aco1G7Nk5F",
     "notes": "Telling a real story with video and images — same muscles as "
              "making a short."},
    {"title": "Smithsonian: Visualizing Democracy",
     "subject": "Social Studies",
     "url": "https://learninglab.si.edu/collections/visualizing-democracy/bLxR9cwU5da7UFW5",
     "notes": "National Portrait Gallery — civics told through pictures "
              "instead of textbook paragraphs."},
    {"title": "Smithsonian: Investigating Civic Ideals through Art",
     "subject": "Social Studies",
     "url": "https://learninglab.si.edu/collections/investigating-civic-ideals-through-art-cultivating-learning/TtWkKlpzFNqM8LrB",
     "notes": "Smithsonian American Art Museum — what freedom and fairness "
              "look like when an artist draws them."},
    {"title": "Smithsonian: We Make History — A Guide for Students",
     "subject": "History",
     "url": "https://learninglab.si.edu/collections/we-make-history-a-guide-for-students/OeX0WzB7hkl4Lujp",
     "notes": "Anacostia Community Museum — a student-facing guide to "
              "researching and telling history yourself."},
]

# --- Foundations Track: the hand-curated life-skills / financial-literacy
# library that is the whole differentiator in Compass_Homeschool_Market_
# Strategy.docx. Deliberately a fixed, ownable set of ~14 tight modules (not
# an AI content firehose), each tagged to real WA_SUBJECTS so finishing one
# attributes compliance hours exactly like a quest. objectives = what he can
# do afterwards; activities = concrete do-it tasks, one per line. source_url
# points at a reputable free resource to actually work from. Placeholder
# starter content — the parent edits/extends it from the Foundations admin.
FOUNDATIONS_MODULE_SEEDS = [
    # ---- Financial Literacy ----
    {"title": "Where Your Money Goes", "pillar": "Financial Literacy",
     "subjects": "Mathematics, Occupational Education", "est_hours": 1.5,
     "source_url": "https://consumer.gov/section/managing-your-money",
     "description": "Build a simple budget and see where money actually leaks out.",
     "objectives": "Tell the difference between a need and a want, split money "
                   "with a save/spend/give plan, and track a week of real spending.",
     "activities": "Track everything you (or the family) spend for 3 days\n"
                   "Sort each one into needs vs wants\n"
                   "Build a save/spend/give split for $50\n"
                   "Find one 'want' you'd cut and say why"},
    {"title": "How Banking Actually Works", "pillar": "Financial Literacy",
     "subjects": "Mathematics, Occupational Education", "est_hours": 1.5,
     "source_url": "https://www.mymoney.gov/",
     "description": "Checking vs savings, debit vs credit, and what interest really is.",
     "objectives": "Explain what a bank does with your money, why savings earns "
                   "interest, and how a debit card differs from a credit card.",
     "activities": "Explain checking vs savings in your own words\n"
                   "Calculate a year of interest on $200 at 4%\n"
                   "List 3 ways a debit card and a credit card differ\n"
                   "Read a sample bank statement and find the balance"},
    {"title": "Taxes 101: Why Your Paycheck Shrinks", "pillar": "Financial Literacy",
     "subjects": "Mathematics, Occupational Education", "est_hours": 1.0,
     "source_url": "https://apps.irs.gov/app/understandingTaxes/student/index.jsp",
     "description": "What all those deductions on a paycheck are, in plain terms.",
     "objectives": "Read a pay stub, explain gross vs net pay, and describe what "
                   "income tax pays for.",
     "activities": "Label every line on a sample pay stub\n"
                   "Work out net pay from a $600 gross check\n"
                   "Name 3 things taxes pay for that you use\n"
                   "Explain 'gross vs net' to a parent"},
    # ---- Digital Literacy ----
    {"title": "Spotting Fakes: News, Scams & AI", "pillar": "Digital Literacy",
     "subjects": "Occupational Education, Reading", "est_hours": 1.5,
     "source_url": "https://www.commonsense.org/education/digital-citizenship",
     "description": "Tell real from fake online — headlines, scams, and AI images.",
     "objectives": "Fact-check a claim, spot the signs of a phishing scam, and "
                   "explain why an AI image can look real but be fake.",
     "activities": "Fact-check a viral claim using two sources\n"
                   "Spot 3 red flags in a scam email or DM\n"
                   "Find the tells in an AI-generated image\n"
                   "Write your own rule for 'is this legit?'"},
    {"title": "Your Digital Footprint", "pillar": "Digital Literacy",
     "subjects": "Occupational Education", "est_hours": 1.0,
     "source_url": "https://beinternetawesome.withgoogle.com/",
     "description": "What the internet remembers about you, and how to control it.",
     "objectives": "Explain what a digital footprint is, adjust a privacy setting, "
                   "and decide what's safe to post.",
     "activities": "Search your own name and see what comes up\n"
                   "Change one privacy setting on an app you use\n"
                   "Build a strong passphrase you can remember\n"
                   "List 3 things you'd never post, and why"},
    # ---- Career Readiness ----
    {"title": "What Do People Actually Do All Day?", "pillar": "Career Readiness",
     "subjects": "Occupational Education", "est_hours": 1.0,
     "source_url": "https://www.bls.gov/ooh/",
     "description": "Explore real jobs — what they pay, and what they're actually like.",
     "objectives": "Research a career's day-to-day, pay, and training, and connect "
                   "it to something you're into.",
     "activities": "Pick 3 jobs tied to something you like\n"
                   "Look up pay and training for each\n"
                   "Interview an adult about their actual workday\n"
                   "Rank the 3 and say why"},
    {"title": "Your First Résumé", "pillar": "Career Readiness",
     "subjects": "Writing, Occupational Education", "est_hours": 1.5,
     "source_url": "https://www.careeronestop.org/GetMyFuture/Toolkit/toolkit.aspx",
     "description": "Put together a real one-page résumé, even with no job yet.",
     "objectives": "Write a résumé that turns projects, chores, and hobbies into "
                   "real experience.",
     "activities": "List everything you've done that took skill\n"
                   "Turn 3 of them into résumé bullet points\n"
                   "Draft a clean one-page résumé\n"
                   "Have a parent mark it up"},
    # ---- Health & Wellness ----
    {"title": "Fuel & Sleep: Running Your Body", "pillar": "Health & Wellness",
     "subjects": "Health, Science", "est_hours": 1.0,
     "source_url": "https://www.myplate.gov/",
     "description": "How food and sleep actually change how you feel and think.",
     "objectives": "Read a nutrition label, plan a balanced plate, and explain why "
                   "sleep affects mood and focus.",
     "activities": "Read the label on something in the kitchen\n"
                   "Build a balanced plate for one meal\n"
                   "Track your sleep for 3 nights\n"
                   "Note how you felt on the best vs worst night"},
    {"title": "Handling Stress & Big Feelings", "pillar": "Health & Wellness",
     "subjects": "Health", "est_hours": 1.0,
     "source_url": "https://kidshealth.org/en/teens/stress.html",
     "description": "Practical tools for when things feel like too much.",
     "objectives": "Name what stress feels like in your body and use two ways to "
                   "bring it down.",
     "activities": "List your own early warning signs of stress\n"
                   "Try a box-breathing round (4-4-4-4)\n"
                   "Pick two reset moves that work for you\n"
                   "Make a 'when I'm overwhelmed' plan"},
    # ---- Life Skills ----
    {"title": "Cook Three Real Meals", "pillar": "Life Skills",
     "subjects": "Occupational Education, Health", "est_hours": 2.0,
     "source_url": "https://www.allrecipes.com/recipes/739/everyday-cooking/quick-and-easy/",
     "description": "Actually feed yourself — breakfast, lunch, and a dinner.",
     "objectives": "Follow a recipe, use a knife safely, and cook three meals "
                   "start to finish with cleanup.",
     "activities": "Cook a breakfast from scratch\n"
                   "Make a lunch that isn't from a package\n"
                   "Cook one dinner for the family\n"
                   "Clean the kitchen fully after each"},
    {"title": "Fix-It Basics", "pillar": "Life Skills",
     "subjects": "Occupational Education", "est_hours": 1.5,
     "source_url": "https://www.ifixit.com/Guide",
     "description": "Small repairs so you're not stuck waiting on someone else.",
     "objectives": "Use basic tools to handle common fixes — a screw, a bike tire, "
                   "a battery, a clog.",
     "activities": "Learn what's in the toolbox and what each does\n"
                   "Tighten or fix something that's loose or broken\n"
                   "Re-inflate or patch a bike tire\n"
                   "Fix one thing you'd normally ask an adult to do"},
    {"title": "Doing Your Own Laundry", "pillar": "Life Skills",
     "subjects": "Occupational Education", "est_hours": 1.0,
     "source_url": "https://www.tide.com/en-us/how-to-wash-clothes/how-to-do-laundry",
     "description": "Wash your own clothes without turning everything pink.",
     "objectives": "Sort, wash, dry, and fold a load without shrinking or "
                   "staining anything.",
     "activities": "Sort a real pile by color and fabric\n"
                   "Run a full wash + dry cycle yourself\n"
                   "Fold and put away the whole load\n"
                   "Learn what one laundry symbol means"},
    # ---- Civics ----
    {"title": "How a Law Actually Gets Made", "pillar": "Civics",
     "subjects": "Social Studies", "est_hours": 1.0,
     "source_url": "https://www.icivics.org/games",
     "description": "From idea to law — and where a regular person can push.",
     "objectives": "Trace a bill from idea to law and name one point where "
                   "citizens can influence it.",
     "activities": "Map the steps a bill takes to become law\n"
                   "Find a real bill in the news right now\n"
                   "Name who represents your area\n"
                   "Write what you'd tell them about one issue"},
    {"title": "Your Rights & Local Government", "pillar": "Civics",
     "subjects": "Social Studies", "est_hours": 1.0,
     "source_url": "https://www.usa.gov/local-governments",
     "description": "What the government near you does, and what rights you have.",
     "objectives": "Name what local government handles and list a few of your "
                   "basic rights.",
     "activities": "List 5 things your city/county actually runs\n"
                   "Find when the next local meeting is\n"
                   "Name 3 rights in the Bill of Rights\n"
                   "Pick one local problem and who to ask about it"},
]

# Sites the curriculum/electives above actually require a login for.
# required=True -> always needed, regardless of elective picks.
# required=False -> only needed if one of "electives" is currently selected
# (names must match elective_pool entries).
ACCOUNT_SERVICES = {
    "Khan Academy": {
        "url": "https://www.khanacademy.org/",
        "tie": "Math, Science, Social Studies, History, Art & Music, Occ. Ed",
        "required": True, "electives": []},
    "CommonLit": {
        "url": "https://www.commonlit.org/", "tie": "Reading",
        "required": True, "electives": []},
    "ReadWorks": {
        "url": "https://www.readworks.org/", "tie": "Writing",
        "required": True, "electives": []},
    "CK-12": {
        "url": "https://www.ck12.org/student/", "tie": "Science",
        "required": True, "electives": []},
    "Nitro Type": {
        "url": "https://www.nitrotype.com/",
        "tie": "Typing practice — general skill, fun/competitive",
        "required": True, "electives": []},
    "Kahoot!": {
        "url": "https://kahoot.com/", "tie": "Quiz & review games",
        "required": True, "electives": []},
    "Smithsonian Learning Lab": {
        "url": "https://learninglab.si.edu/",
        "tie": "History/Social Studies enrichment — build collections from "
               "real archives",
        "required": True, "electives": []},
    "Canva for Education": {
        "url": "https://www.canva.com/education/",
        "tie": "Design tool for posters, slides & presentations (any subject)",
        "required": True, "electives": []},
    "Duolingo": {
        "url": "https://www.duolingo.com/", "tie": "Elective — World Language",
        "required": False, "electives": ["World Language — Spanish"]},
    "Code.org": {
        "url": "https://code.org/", "tie": "Elective — Computer Science",
        "required": False,
        "electives": ["Computer Science — Intro to Coding"]},
    "Scratch": {
        "url": "https://scratch.mit.edu/",
        "tie": "Elective — Computer Science (creative/game coding)",
        "required": False,
        "electives": ["Computer Science — Intro to Coding",
                      "Introduction to Computer Science"]},
    "Chess.com": {
        "url": "https://www.chess.com/", "tie": "Elective — Chess",
        "required": False, "electives": ["Chess"]},
    "Lichess": {
        "url": "https://lichess.org/",
        "tie": "Elective — Chess (free, no paywall — alternative to Chess.com)",
        "required": False, "electives": ["Chess"]},
    "Tinkercad": {
        "url": "https://www.tinkercad.com/",
        "tie": "Elective — Automation & Robotics (3D design for robot parts)",
        "required": False, "electives": ["Automation & Robotics (VEX)"]},
}

# Manual items on the parent launch checklist — things the app can't verify itself.
MANUAL_CHECKLIST_ITEMS = [
    {"key": "doi_filed", "label": "Declaration of Intent filed with the district",
     "help": "WA requirement — due Sept 15, or within 2 weeks of a mid-year start."},
    {"key": "curriculum_reviewed", "label": "Curriculum & resource links reviewed",
     "help": "Skim the links in each subject block on the My Week tab — swap out "
             "anything that doesn't fit."},
    {"key": "assessment_plan", "label": "Annual assessment plan decided",
     "help": "RCW 28A.200.010: a standardized achievement test by a qualified "
             "individual, OR a written assessment by a certificated person — "
             "your choice, once a year, kept in his records (not sent to the "
             "district). Full text in the Assessments tab. Record it there "
             "once scheduled."},
    {"key": "schedule_reviewed", "label": "Weekly schedule reviewed for this student",
     "help": "Block times/subjects live in WEEKLY_SCHEDULE in app.py — adjust "
             "before day one if needed."},
    {"key": "backup_plan", "label": "Records backup plan in place",
     "help": "Export hours/grades/assessments periodically (Export tab) and keep "
             "a copy off this machine."},
]

# Manual items on the student's Day 1 checklist — quick orientation checks.
DAY1_MANUAL_ITEMS = [
    {"key": "day1_schedule", "label": "I looked over my Weekly Schedule",
     "help": "Check the 🗓 My Week tab so you know what's coming each day."},
    {"key": "day1_mark_done", "label": "I know how to mark a block as Done",
     "help": "On the 📅 Today tab, click \"✅ Done, got it\" (or \"😕 Done, "
             "still fuzzy\" if it didn't click) next to a subject once you "
             "finish it — that sends it to a parent for approval."},
    {"key": "day1_quizzes", "label": "I found my Quizzes tab",
     "help": "📝 Quizzes tests what you've learned and saves your score "
             "straight to your grades."},
]

# Static, auto-gradable quiz bank: subject -> topic -> multiple-choice questions.
# Add topics/questions here as he progresses through material.
QUIZ_BANK = {
    "Mathematics": {
        "Linear Equations & Slope": [
            {"q": "What is the slope of the line y = 3x + 5?",
             "choices": ["2", "3", "5", "-3"], "answer": "3"},
            {"q": "In the equation y = mx + b, what does b represent?",
             "choices": ["The slope", "The y-intercept", "The x-intercept",
                         "The rate of change"], "answer": "The y-intercept"},
            {"q": "Solve for x: 2x + 4 = 12",
             "choices": ["2", "4", "6", "8"], "answer": "4"},
            {"q": "A line has a slope of 0. What does that mean?",
             "choices": ["It's vertical", "It's horizontal", "It passes through the origin",
                         "It's undefined"], "answer": "It's horizontal"},
            {"q": "What is the slope between points (1,2) and (3,6)?",
             "choices": ["1", "2", "3", "4"], "answer": "2"},
        ],
        "Ratios, Proportions & Percents": [
            {"q": "If 3 apples cost $1.50, how much do 5 apples cost?",
             "choices": ["$2.00", "$2.50", "$3.00", "$5.00"], "answer": "$2.50"},
            {"q": "What is 25% of 80?",
             "choices": ["15", "20", "25", "30"], "answer": "20"},
            {"q": "Simplify the ratio 12:16",
             "choices": ["3:4", "4:3", "6:8", "2:3"], "answer": "3:4"},
            {"q": "A $40 shirt is 20% off. What's the sale price?",
             "choices": ["$32", "$30", "$36", "$28"], "answer": "$32"},
            {"q": "A map scale is 1 inch = 10 miles. How many miles is 4.5 inches?",
             "choices": ["40", "45", "50", "35"], "answer": "45"},
        ],
        "Math Computation Practice": [
            {"q": "347 + 586 = ?",
             "choices": ["833", "923", "933", "943"], "answer": "933"},
            {"q": "804 − 259 = ?",
             "choices": ["535", "545", "555", "645"], "answer": "545"},
            {"q": "27 × 14 = ?",
             "choices": ["368", "378", "388", "398"], "answer": "378"},
            {"q": "156 ÷ 12 = ?",
             "choices": ["11", "12", "13", "14"], "answer": "13"},
            {"q": "3/4 + 1/8 = ?",
             "choices": ["7/8", "4/12", "1/2", "5/8"], "answer": "7/8"},
        ],
    },
    "Science": {
        "Forces & Motion": [
            {"q": "What is Newton's First Law also known as?",
             "choices": ["Law of Inertia", "Law of Acceleration", "Law of Action-Reaction",
                         "Law of Gravity"], "answer": "Law of Inertia"},
            {"q": "Force = mass × ?",
             "choices": ["Velocity", "Acceleration", "Distance", "Time"],
             "answer": "Acceleration"},
            {"q": "What unit is force measured in?",
             "choices": ["Joule", "Newton", "Watt", "Pascal"], "answer": "Newton"},
            {"q": "An object at rest stays at rest unless acted on by a(n) ___.",
             "choices": ["Unbalanced force", "Balanced force", "Vacuum", "Magnetic field"],
             "answer": "Unbalanced force"},
            {"q": "Which has more inertia?",
             "choices": ["A bowling ball", "A tennis ball", "A ping pong ball", "A feather"],
             "answer": "A bowling ball"},
        ],
        "Cells & Body Systems": [
            {"q": "What is the basic unit of life?",
             "choices": ["Atom", "Cell", "Tissue", "Organ"], "answer": "Cell"},
            {"q": "Which organelle is known as the powerhouse of the cell?",
             "choices": ["Nucleus", "Ribosome", "Mitochondria", "Golgi body"],
             "answer": "Mitochondria"},
            {"q": "Which body system transports oxygen and nutrients?",
             "choices": ["Digestive", "Circulatory", "Nervous", "Skeletal"],
             "answer": "Circulatory"},
            {"q": "What is the main function of red blood cells?",
             "choices": ["Fight infection", "Carry oxygen", "Digest food", "Send signals"],
             "answer": "Carry oxygen"},
            {"q": "Which organ pumps blood through the body?",
             "choices": ["Lungs", "Liver", "Heart", "Kidney"], "answer": "Heart"},
        ],
    },
    "Social Studies": {
        "Civics & Government Basics": [
            {"q": "How many branches does the U.S. federal government have?",
             "choices": ["2", "3", "4", "5"], "answer": "3"},
            {"q": "Which branch makes laws?",
             "choices": ["Executive", "Legislative", "Judicial", "Local"],
             "answer": "Legislative"},
            {"q": "How many years is a U.S. President's term?",
             "choices": ["2", "4", "6", "8"], "answer": "4"},
            {"q": "What document begins with \"We the People\"?",
             "choices": ["Declaration of Independence", "U.S. Constitution",
                         "Bill of Rights", "Articles of Confederation"],
             "answer": "U.S. Constitution"},
            {"q": "Which branch interprets laws?",
             "choices": ["Executive", "Legislative", "Judicial", "Congressional"],
             "answer": "Judicial"},
        ],
        "Economics Basics": [
            {"q": "What is scarcity?",
             "choices": ["Unlimited resources", "Limited resources & unlimited wants",
                         "A type of tax", "A government program"],
             "answer": "Limited resources & unlimited wants"},
            {"q": "What term describes the study of how people make choices under scarcity?",
             "choices": ["Sociology", "Economics", "Civics", "Geography"],
             "answer": "Economics"},
            {"q": "What is inflation?",
             "choices": ["A rise in prices over time", "A drop in unemployment",
                         "A type of interest rate", "A government law"],
             "answer": "A rise in prices over time"},
            {"q": "What describes how price and quantity relate to buyers and sellers?",
             "choices": ["Supply and demand", "A tax law", "A banking rule",
                         "A trade agreement"], "answer": "Supply and demand"},
            {"q": "What is a budget?",
             "choices": ["A plan for income and spending", "A type of loan",
                         "A savings account", "A tax form"],
             "answer": "A plan for income and spending"},
        ],
        "Maps, Diagrams & Reference Skills": [
            {"q": "On most maps, which direction is at the top?",
             "choices": ["South", "North", "East", "West"], "answer": "North"},
            {"q": "To find a specific topic quickly in a book, which part "
                  "should you check?",
             "choices": ["Glossary", "Index", "Table of Contents", "Preface"],
             "answer": "Index"},
            {"q": "On a map, what does the legend (or key) explain?",
             "choices": ["The map's title", "What the symbols and colors mean",
                         "The distance scale only", "The compass rose only"],
             "answer": "What the symbols and colors mean"},
            {"q": "A map scale shows 1 inch = 50 miles. Two cities are 3 inches "
                  "apart on the map. How far apart are they really?",
             "choices": ["50 miles", "100 miles", "150 miles", "200 miles"],
             "answer": "150 miles"},
            {"q": "Which reference source would best help you find the meaning "
                  "of a word?",
             "choices": ["Atlas", "Dictionary", "Almanac", "Encyclopedia"],
             "answer": "Dictionary"},
        ],
    },
    "History": {
        "American Revolution": [
            {"q": "What year was the Declaration of Independence signed?",
             "choices": ["1774", "1776", "1781", "1789"], "answer": "1776"},
            {"q": "Who was the first President of the United States?",
             "choices": ["Thomas Jefferson", "John Adams", "George Washington",
                         "Benjamin Franklin"], "answer": "George Washington"},
            {"q": "What battles are considered the start of the Revolutionary War?",
             "choices": ["Boston Tea Party", "Battles of Lexington and Concord",
                         "Signing of the Constitution", "Louisiana Purchase"],
             "answer": "Battles of Lexington and Concord"},
            {"q": "What was the main colonial complaint that sparked revolt?",
             "choices": ["Too many holidays", "Taxation without representation",
                         "Lack of farmland", "Foreign wars"],
             "answer": "Taxation without representation"},
            {"q": "Which treaty ended the Revolutionary War?",
             "choices": ["Treaty of Ghent", "Treaty of Paris", "Treaty of Versailles",
                         "Treaty of Tordesillas"], "answer": "Treaty of Paris"},
        ],
        "Civil Rights Movement": [
            {"q": "Who is known for the \"I Have a Dream\" speech?",
             "choices": ["Malcolm X", "Rosa Parks", "Martin Luther King Jr.", "John Lewis"],
             "answer": "Martin Luther King Jr."},
            {"q": "What Supreme Court case ended school segregation?",
             "choices": ["Plessy v. Ferguson", "Brown v. Board of Education", "Roe v. Wade",
                         "Marbury v. Madison"], "answer": "Brown v. Board of Education"},
            {"q": "Rosa Parks became famous for refusing to give up her seat on a ___.",
             "choices": ["Train", "Bus", "Plane", "Bench"], "answer": "Bus"},
            {"q": "What year was the Civil Rights Act passed?",
             "choices": ["1954", "1960", "1964", "1970"], "answer": "1964"},
            {"q": "What was the name of the 1963 march where MLK spoke?",
             "choices": ["March on Washington", "Selma March", "Freedom Ride",
                         "March on Montgomery"], "answer": "March on Washington"},
        ],
    },
    "Reading": {
        "The Giver": [
            {"q": "What is the name of the main character in The Giver?",
             "choices": ["Jonas", "Asher", "Gabriel", "Fiona"], "answer": "Jonas"},
            {"q": "What role is Jonas assigned in the community?",
             "choices": ["Receiver of Memory", "Nurturer", "Engineer", "Doctor"],
             "answer": "Receiver of Memory"},
            {"q": "What does the community use to suppress strong emotions?",
             "choices": ["Medication", "Sameness/strict rules", "Music", "Isolation"],
             "answer": "Sameness/strict rules"},
            {"q": "Who transfers memories to Jonas?",
             "choices": ["The Giver", "The Elder", "His father", "The Chief Elder"],
             "answer": "The Giver"},
            {"q": "What color does Jonas begin to see that others can't?",
             "choices": ["Blue", "Red", "Green", "Yellow"], "answer": "Red"},
        ],
        "Number the Stars": [
            {"q": "Where is Number the Stars set?",
             "choices": ["Germany", "Denmark", "France", "Poland"], "answer": "Denmark"},
            {"q": "Who is Annemarie trying to help protect?",
             "choices": ["Her brother", "Her best friend Ellen, who is Jewish",
                         "A soldier", "Her teacher"],
             "answer": "Her best friend Ellen, who is Jewish"},
            {"q": "What historical event is the backdrop of the story?",
             "choices": ["World War I", "The Holocaust/WWII", "The Cold War",
                         "The French Revolution"], "answer": "The Holocaust/WWII"},
            {"q": "What do Annemarie and her family do to help Ellen's family?",
             "choices": ["Hide them in their home", "Report them to authorities",
                         "Send them away immediately", "Ignore them"],
             "answer": "Hide them in their home"},
            {"q": "How does the Danish resistance help Jewish families escape?",
             "choices": ["Smuggle them to Sweden by boat", "Fly them to America",
                         "Hide them in the mountains", "Send them by train to Norway"],
             "answer": "Smuggle them to Sweden by boat"},
        ],
        "Vocabulary in Context": [
            {"q": "\"The archaeologists were astonished by the artifact's "
                  "pristine condition.\" Pristine most nearly means:",
             "choices": ["Damaged", "Unspoiled", "Ancient", "Valuable"],
             "answer": "Unspoiled"},
            {"q": "Choose the word that means the OPPOSITE of \"reluctant\":",
             "choices": ["Eager", "Hesitant", "Unwilling", "Nervous"],
             "answer": "Eager"},
            {"q": "\"Her explanation was so ambiguous that no one understood "
                  "what she meant.\" Ambiguous most nearly means:",
             "choices": ["Clear", "Unclear", "Loud", "Short"], "answer": "Unclear"},
            {"q": "Choose the word that means the SAME as \"diligent\":",
             "choices": ["Lazy", "Hardworking", "Careless", "Slow"],
             "answer": "Hardworking"},
            {"q": "\"The coach's candid feedback surprised the team.\" "
                  "Candid most nearly means:",
             "choices": ["Harsh", "Honest", "Confusing", "Quiet"], "answer": "Honest"},
        ],
    },
    "Writing": {
        "Grammar & Mechanics": [
            {"q": "Which sentence is correctly capitalized?",
             "choices": ["We visited the grand canyon last Summer.",
                         "We visited the Grand Canyon last summer.",
                         "we visited the Grand Canyon last Summer.",
                         "We Visited the Grand Canyon Last Summer."],
             "answer": "We visited the Grand Canyon last summer."},
            {"q": "Which sentence uses correct punctuation?",
             "choices": ["I need eggs milk and bread.",
                         "I need eggs, milk, and bread.",
                         "I need, eggs milk and bread.",
                         "I need eggs milk, and bread"],
             "answer": "I need eggs, milk, and bread."},
            {"q": "Choose the correctly written sentence:",
             "choices": ["Me and him went to the store.",
                         "Him and I went to the store.",
                         "He and I went to the store.",
                         "Me and he went to the store."],
             "answer": "He and I went to the store."},
            {"q": "Which word correctly completes the sentence: \"Neither of "
                  "the boys ___ finished his homework.\"",
             "choices": ["has", "have", "having", "had been"], "answer": "has"},
            {"q": "Which sentence is a run-on and needs to be fixed?",
             "choices": ["I like pizza.",
                         "I like pizza, but I don't like mushrooms.",
                         "I like pizza I don't like mushrooms.",
                         "Although I like pizza, I don't like mushrooms."],
             "answer": "I like pizza I don't like mushrooms."},
        ],
    },
    "Health": {
        "Nutrition & Body Systems": [
            {"q": "Which nutrient is the body's main source of quick energy?",
             "choices": ["Protein", "Carbohydrates", "Fat", "Water"],
             "answer": "Carbohydrates"},
            {"q": "Which vitamin does the body produce when skin is exposed "
                  "to sunlight?",
             "choices": ["Vitamin A", "Vitamin C", "Vitamin D", "Vitamin B12"],
             "answer": "Vitamin D"},
            {"q": "About how much water does the body need daily to "
                  "function well?",
             "choices": ["1 cup", "2 liters (about 8 cups)", "10 liters",
                         "500 mL"], "answer": "2 liters (about 8 cups)"},
            {"q": "Which organ system breaks down food for energy?",
             "choices": ["Respiratory system", "Digestive system",
                         "Skeletal system", "Nervous system"],
             "answer": "Digestive system"},
            {"q": "Which of these is a sign of dehydration?",
             "choices": ["Dark yellow urine", "Frequent urination",
                         "Increased energy", "Lower heart rate"],
             "answer": "Dark yellow urine"},
        ],
        "First Aid & Safety": [
            {"q": "What's the first thing you should do for a minor cut?",
             "choices": ["Apply a bandage immediately", "Clean it with water",
                         "Ignore it", "Apply ice only"],
             "answer": "Clean it with water"},
            {"q": "What does the 'R' stand for in R.I.C.E. treatment for a sprain?",
             "choices": ["Run", "Rest", "Rotate", "Reduce"], "answer": "Rest"},
            {"q": "If someone is choking and can't speak or cough, what "
                  "should you do?",
             "choices": ["Give them water",
                         "Perform abdominal thrusts (Heimlich maneuver)",
                         "Wait for it to pass", "Have them lie down"],
             "answer": "Perform abdominal thrusts (Heimlich maneuver)"},
            {"q": "Which number do you call for a medical emergency in the US?",
             "choices": ["411", "911", "211", "611"], "answer": "911"},
            {"q": "Which is a healthy way to handle peer pressure around substances?",
             "choices": ["Give in to fit in",
                         "Have a planned response ready and say no",
                         "Avoid the topic forever", "Pretend you don't hear"],
             "answer": "Have a planned response ready and say no"},
        ],
        "Neurodiversity & Mental Health": [
            {"q": "Autism is best described as:",
             "choices": ["A disease that needs to be cured",
                         "A developmental difference in how the brain "
                         "processes information",
                         "A rare mental illness",
                         "Something that only affects young children"],
             "answer": "A developmental difference in how the brain "
                      "processes information"},
            {"q": "Which statement about autism is TRUE?",
             "choices": ["No two autistic people are exactly alike — it's "
                        "called a spectrum for a reason",
                        "All autistic people are nonverbal",
                        "Autism only affects boys",
                        "People grow out of autism"],
             "answer": "No two autistic people are exactly alike — it's "
                      "called a spectrum for a reason"},
            {"q": "What does it mean to call something a 'mental health' issue?",
             "choices": ["It's not real",
                        "It relates to emotional, psychological, and "
                        "social well-being",
                        "It only affects adults",
                        "It's always visible to others"],
             "answer": "It relates to emotional, psychological, and "
                      "social well-being"},
            {"q": "A friend tells you they're struggling with their mental "
                  "health. What's the most helpful response?",
             "choices": ["Tell them to just get over it",
                        "Listen without judgment and help them find support",
                        "Ignore it, it's not your business",
                        "Tell everyone else about it"],
             "answer": "Listen without judgment and help them find support"},
            {"q": "Which of these is a healthy coping strategy for stress?",
             "choices": ["Talking to someone you trust",
                        "Bottling it up completely",
                        "Avoiding everyone forever",
                        "Pretending it doesn't exist"],
             "answer": "Talking to someone you trust"},
        ],
    },
}

# Fun facts tied to 8th-grade subjects — pure trivia, not graded.
TRIVIA_BANK = [
    {"subject": "Math", "fact": "Zero was never used as a number in ancient "
     "Rome — Roman numerals have no symbol for it at all."},
    {"subject": "Math", "fact": "The '=' sign was invented in 1557 by Robert "
     "Recorde because he was tired of writing 'is equal to' over and over."},
    {"subject": "Math", "fact": "A 'googol' is the number 1 followed by 100 "
     "zeros — it's where the company Google got its name (with a spelling twist)."},
    {"subject": "Math", "fact": "The Fibonacci sequence shows up constantly "
     "in nature — pinecones, sunflower seeds, even hurricanes follow it."},
    {"subject": "Math", "fact": "Ancient Babylonians used a base-60 number "
     "system — that's why we have 60 minutes in an hour and 60 seconds in "
     "a minute."},
    {"subject": "Science", "fact": "A bolt of lightning is roughly 5 times "
     "hotter than the surface of the sun."},
    {"subject": "Science", "fact": "Honey never spoils — archaeologists have "
     "found 3,000-year-old honey in Egyptian tombs that was still edible."},
    {"subject": "Science", "fact": "Water can boil and freeze at the exact "
     "same time — it's called the 'triple point.'"},
    {"subject": "Science", "fact": "Octopuses have three hearts and blue blood."},
    {"subject": "Science", "fact": "Mount Rainier is an active volcano, not "
     "just a mountain — it's monitored 24/7 for eruption risk."},
    {"subject": "History", "fact": "The Revolutionary War officially ended "
     "almost 2 years after the Battle of Yorktown — the Treaty of Paris "
     "wasn't signed until 1783."},
    {"subject": "History", "fact": "Washington is the only U.S. state named "
     "after a president."},
    {"subject": "History", "fact": "Susan B. Anthony was arrested for voting "
     "in 1872 — decades before women legally gained the right nationwide."},
    {"subject": "History", "fact": "The shortest war in recorded history "
     "lasted about 38 minutes — the Anglo-Zanzibar War of 1896."},
    {"subject": "History", "fact": "The Oregon Trail is nearly 2,000 miles "
     "long — roughly the same distance as driving from Seattle to Chicago."},
    {"subject": "Social Studies", "fact": "The U.S. Constitution is the "
     "oldest still-functioning written national constitution in the world."},
    {"subject": "Social Studies", "fact": "There are 27 amendments to the "
     "Constitution — the first 10 are called the Bill of Rights."},
    {"subject": "Social Studies", "fact": "A U.S. president must be at "
     "least 35 years old, but there's no maximum age requirement."},
    {"subject": "Reading/Writing", "fact": "Shakespeare invented or "
     "popularized over 1,700 words still used in English today, including "
     "'eyeball' and 'lonely.'"},
    {"subject": "Reading/Writing", "fact": "The dot over a lowercase 'i' or "
     "'j' has an actual name: it's called a 'tittle.'"},
    {"subject": "Health", "fact": "Your bones are actually stronger than "
     "steel by weight — but way lighter."},
    {"subject": "Health", "fact": "It takes about 20 minutes for your brain "
     "to register that your stomach is full."},
    {"subject": "Health", "fact": "Humans shed about 500 million skin cells "
     "every single day."},
    {"subject": "Health", "fact": "April is Autism Acceptance Month, and May "
     "is Mental Health Awareness Month in the U.S."},
    {"subject": "Health", "fact": "The word 'autism' comes from the Greek "
     "word 'autos,' meaning 'self' — first used in the early 1900s."},
    {"subject": "Health", "fact": "About 1 in 4 adults experiences a mental "
     "health condition in any given year — it's more common than most "
     "people realize."},
    {"subject": "Health", "fact": "The term 'neurodiversity' was coined in "
     "the late 1990s to describe the idea that brain differences are "
     "natural variation, not deficits."},
    {"subject": "Health", "fact": "Openly autistic people and people who've "
     "spoken about mental health struggles include scientists, athletes, "
     "and artists across nearly every field."},
]

WEEKLY_SCHEDULE = {
    "Monday": [("Mathematics", "08:30", "10:00"), ("Reading", "10:00", "11:00"),
               ("Writing", "11:00", "11:30"), ("Science", "12:00", "13:30"),
               ("Social Studies", "13:30", "14:30")],
    "Tuesday": [("Mathematics", "08:30", "10:00"), ("Reading", "10:00", "11:00"),
                ("Writing", "11:00", "11:30"),
                ("Mathematics", "11:30", "12:00", "Mathematics — IXL"),
                ("History", "12:00", "13:30"),
                ("Science", "13:30", "14:30")],
    "Wednesday": [("Mathematics", "08:30", "09:30"), ("Reading", "09:30", "10:30"),
                  ("Writing", "10:30", "11:00"), ("Science", "11:30", "13:00"),
                  ("History", "13:00", "14:00")],
    "Thursday": [("Mathematics", "08:30", "09:30"), ("Reading", "09:30", "10:15"),
                 ("Writing", "10:15", "10:30"),
                 ("Mathematics", "10:30", "11:00", "Mathematics — IXL"),
                 ("Social Studies", "11:00", "12:30"),
                 ("Occupational Education", "12:30", "13:15"),
                 ("Health", "13:15", "14:00")],
    "Friday": [("Mathematics", "08:30", "09:00"), ("Reading", "09:00", "09:30"),
               ("Art & Music Appreciation", "09:30", "11:30"),
               ("Electives", "11:30", "13:30")],
}

# Student-facing quest names — display only, never touches the underlying
# `subject` value used for hours/compliance tracking. Parent mode keeps
# showing real subject names (render_day_blocks only runs in Student mode).
QUEST_TITLES = {
    "Mathematics": "⚔️ Math Quest", "Reading": "📖 Story Quest",
    "Writing": "✍️ Word Smith", "Science": "🔬 Lab Mission",
    "Social Studies": "🏛️ Civics Quest", "History": "📜 History Quest",
    "Health": "🛡️ Wellness Quest", "Occupational Education": "💼 Life Skills Quest",
    "Art & Music Appreciation": "🎨 Creative Studio", "Electives": "🎮 Bonus Round",
}

# A fixed pop-art color per subject — same idea as QUEST_POP_COLORS on the
# Quest Board, but a stable mapping here so each subject always reads as
# the same color across the app (Math is always blue, etc.) rather than
# shifting per render.
QUEST_SUBJECT_COLORS = {
    "Mathematics": "#4FC3E8", "Reading": "#B084F0", "Writing": "#FF5FA2",
    "Science": "#6FCF7A", "Social Studies": "#FF9F45", "History": "#FFD23F",
    "Health": "#6FCF7A", "Occupational Education": "#FF9F45",
    "Art & Music Appreciation": "#FF5FA2", "Electives": "#4FC3E8",
}

def planned_hours_by_subject():
    """Weekly target hours per subject, derived by adding up WEEKLY_SCHEDULE.

    This used to be a hand-typed dict kept alongside the schedule, which
    silently drifted out of sync with it (Writing was listed as 2.0 while the
    schedule only allotted 1.75, so a perfect week still showed as "behind";
    Mathematics ran the other way at 6.0 vs 6.5). Deriving it means the
    schedule is the single source of truth and a perfect week always reads as
    100% — edit WEEKLY_SCHEDULE and these targets follow automatically.
    """
    totals = {}
    for blocks in WEEKLY_SCHEDULE.values():
        for block in blocks:
            subject, start, end = block[0], block[1], block[2]
            totals[subject] = round(totals.get(subject, 0.0)
                                    + block_hours(start, end), 2)
    return totals


def fmt_date(d):
    """ISO date string (or date/None/NaN) -> MM-DD-YYYY for display.
    Storage stays ISO everywhere else so sorting/comparisons work as-is."""
    if d is None or d == "" or (isinstance(d, float) and pd.isna(d)):
        return ""
    if isinstance(d, str):
        try:
            d = datetime.strptime(d[:10], "%Y-%m-%d").date()
        except ValueError:
            return d
    return d.strftime("%m-%d-%Y")


def letter_grade(pct):
    for cutoff, letter in [(93, "A"), (90, "A-"), (87, "B+"), (83, "B"),
                           (80, "B-"), (77, "C+"), (73, "C"), (70, "C-"),
                           (67, "D+"), (63, "D"), (60, "D-")]:
        if pct >= cutoff:
            return letter
    return "F"


QUIZ_SEC_PER_QUESTION = 30  # minimum expected seconds per question


def format_elapsed(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


# Daily wellness check-in — separate from hour-compliance logging (see
# render_health_habits_checkin for why).
HEALTH_HABITS = [
    {"key": "exercise", "emoji": "🏃", "label": "Moved my body"},
    {"key": "water", "emoji": "💧", "label": "Drank water"},
    {"key": "sleep", "emoji": "😴", "label": "Slept enough"},
    {"key": "nutrition", "emoji": "🥗", "label": "Ate something decent"},
]

RATING_SCALE = ["😞", "😕", "😐", "🙂", "😄"]  # index+1 = stored 1-5 rating

# One-tap answers to "what got in the way today?". Deliberately tappable
# instead of a text box: a 13-year-old will not write a sentence every day,
# but he'll tap a chip — and chips produce data you can actually count and
# chart, which prose never was. "Nailed it" matters as much as the negative
# ones: without a positive option there's no way to tell a genuinely good day
# apart from a day he just skipped the question.
FRICTION_TAGS = [
    "😵‍💫 Confusing", "🥱 Couldn't focus", "🐌 Dragged on", "🏃 Went too fast",
    "📚 Too much of it", "😤 Frustrating", "✨ Nailed it",
]
POSITIVE_FRICTION_TAG = "✨ Nailed it"

# A different physical micro-challenge each day (rotates by date, same way the
# daily trivia does). Small enough to actually do between blocks, and the
# novelty is the point — a fixed "did you stretch?" checkbox goes stale fast.
DAILY_MOVES = [
    "🧘 Two-minute stretch — reach for the ceiling, then your toes",
    "🚶 Ten-minute walk outside. No phone.",
    "💪 As many push-ups as you can in 60 seconds",
    "🦵 Wall sit for 30 seconds. Yes, the whole 30.",
    "🏃 Up and down the stairs five times",
    "🤸 20 jumping jacks",
    "🧍 Stand up and shake it out for one full minute",
    "🎒 Carry something heavy across the yard and back",
    "🕺 One song, dance like nobody's filming. (Nobody is.)",
    "👀 Look out a window at something far away for 60 seconds — eye break",
]

# Interest chips for the Passion Track intake — tappable, so a 13-year-old
# actually fills it in. Stored as a comma list on passion_profile.interests
# and used by the weekly blender to rank which quests to surface first.
INTEREST_OPTIONS = [
    "🎨 Art & drawing", "📚 Comics & manga", "🎬 Video & YouTube",
    "🧱 Building & Legos", "🎮 Video games", "🎵 Music", "🐾 Animals",
    "🚀 Space", "📜 History", "⚽ Sports", "💻 Coding", "🍳 Cooking",
    "🌲 Nature & outdoors", "🚗 Cars & machines", "📖 Reading & stories",
    "🔬 Science experiments", "🗺️ Travel & maps", "🎲 Board games & D&D",
    "🎭 Acting & film", "🤖 Robots & tech",
]


# ------------------------------------------------------------- database
def get_conn():
    conn = connect_database(DB_PATH)
    print(f"Connected database backend: {conn.backend}")
    conn.execute("""CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        grade TEXT, school_year TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS log_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        entry_date TEXT NOT NULL, subject TEXT NOT NULL, hours REAL NOT NULL,
        description TEXT, day_type TEXT DEFAULT 'Instruction',
        status TEXT DEFAULT 'approved', submitted_at TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        assign_date TEXT NOT NULL, subject TEXT NOT NULL, title TEXT NOT NULL,
        score REAL, max_score REAL, notes TEXT, photo_path TEXT, submitted_at TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        assessment_date TEXT NOT NULL, assessment_type TEXT, evaluator TEXT,
        result TEXT, notes TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS student_electives (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        school_year TEXT, elective_name TEXT NOT NULL, selected_date TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS student_books (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        school_year TEXT, title TEXT NOT NULL, author TEXT, ties_to TEXT, link TEXT,
        status TEXT DEFAULT 'planned', selected_date TEXT, finished_date TEXT,
        finished_at TEXT, notes TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        service_name TEXT NOT NULL, url TEXT, username TEXT, password TEXT,
        status TEXT DEFAULT 'not_started', notes TEXT, class_code TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS elective_pool (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
        resource_name TEXT, url TEXT, description TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS book_pool (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        author TEXT, ties_to TEXT, link TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        school_year TEXT, prop_type TEXT NOT NULL, title TEXT NOT NULL,
        secondary TEXT, url TEXT, description TEXT,
        status TEXT DEFAULT 'pending', parent_note TEXT,
        submitted_date TEXT, reviewed_date TEXT, submitted_at TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS fun_project_pool (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        subject TEXT, description TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS student_fun_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        school_year TEXT, title TEXT NOT NULL, subject TEXT, description TEXT,
        status TEXT DEFAULT 'planned', selected_date TEXT, finished_date TEXT,
        finished_at TEXT, notes TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS curriculum_materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        subject TEXT, kind TEXT NOT NULL, file_path TEXT, url TEXT,
        notes TEXT, created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS health_habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        log_date TEXT NOT NULL, exercise INTEGER DEFAULT 0,
        water INTEGER DEFAULT 0, sleep INTEGER DEFAULT 0,
        nutrition INTEGER DEFAULT 0, journal TEXT,
        day_rating INTEGER, mood_rating INTEGER,
        lesson_score INTEGER, lesson_feedback TEXT,
        friction_tags TEXT, rough_subject TEXT, daily_move INTEGER DEFAULT 0,
        UNIQUE(student_id, log_date),
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS holidays (
        id INTEGER PRIMARY KEY AUTOINCREMENT, school_year TEXT,
        start_date TEXT NOT NULL, end_date TEXT NOT NULL, label TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS parent_checkins (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        checkin_date TEXT NOT NULL, notes TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS national_parks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
        state TEXT, lat TEXT, lon TEXT, booklet_url TEXT, region TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS major_cities (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        state TEXT, lat TEXT, lon TEXT)""")
    # migration: older DBs had four separate tables for travel tracking —
    # fold them into one travel_entries table before it gets (re-)created
    # below, so a pre-existing travel_journal's rows are preserved by the
    # rename rather than shadowed by a fresh empty table of the new name.
    if conn.backend == "sqlite":
        existing_tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "travel_journal" in existing_tables and "travel_entries" not in existing_tables:
            conn.execute("ALTER TABLE travel_journal RENAME TO travel_entries")
            existing_tables.discard("travel_journal")
            existing_tables.add("travel_entries")
        for legacy in ("student_park_visits", "student_city_visits", "student_state_visits"):
            if legacy in existing_tables:
                conn.execute(f"DROP TABLE {legacy}")
    # travel_entries: one unified table for every kind of travel log entry
    # (park visit, state visit, city visit, freeform journal entry) — a
    # single entry can tag any combination of state/park/city, or none.
    conn.execute("""CREATE TABLE IF NOT EXISTS travel_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        school_year TEXT, entry_date TEXT NOT NULL, title TEXT NOT NULL,
        content TEXT, photo_path TEXT, tag_state TEXT,
        tag_park_id INTEGER, tag_city_id INTEGER, badge_earned INTEGER DEFAULT 0,
        submitted_at TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id),
        FOREIGN KEY (tag_park_id) REFERENCES national_parks (id),
        FOREIGN KEY (tag_city_id) REFERENCES major_cities (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS link_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        report_date TEXT NOT NULL, url TEXT NOT NULL, description TEXT,
        status TEXT DEFAULT 'pending', parent_note TEXT, resolved_date TEXT,
        submitted_at TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    # Compass two-track model:
    #  - foundations_modules: the hand-curated life-skills/finance library (the
    #    doc's differentiator). subjects uses exact WA_SUBJECTS tags so a
    #    completion attributes compliance hours exactly like a finished quest.
    #  - student_foundations_progress: per-student completion, with the same
    #    hours_logged idempotency flag as student_fun_projects.
    #  - passion_profile: the interest/values intake result, one row per student.
    #  - weekly_plan_items: the blender's output for a given (student, week),
    #    each item pointing back at a quest (passion) or a module (foundations).
    conn.execute("""CREATE TABLE IF NOT EXISTS foundations_modules (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL UNIQUE,
        pillar TEXT NOT NULL, description TEXT, objectives TEXT, activities TEXT,
        subjects TEXT, est_hours REAL DEFAULT 1.0, source_url TEXT,
        sort_order INTEGER DEFAULT 0, active INTEGER DEFAULT 1)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS student_foundations_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        module_id INTEGER NOT NULL, status TEXT DEFAULT 'assigned',
        completed_at TEXT, hours_logged INTEGER DEFAULT 0,
        UNIQUE(student_id, module_id),
        FOREIGN KEY (student_id) REFERENCES students (id),
        FOREIGN KEY (module_id) REFERENCES foundations_modules (id))""")
    # NB: "values" is a reserved SQL keyword — the column is core_values.
    conn.execute("""CREATE TABLE IF NOT EXISTS passion_profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL UNIQUE,
        interests TEXT, core_values TEXT, updated_at TEXT,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS weekly_plan_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        week_start TEXT NOT NULL, kind TEXT NOT NULL, ref_id INTEGER,
        title TEXT, subjects TEXT, est_hours REAL DEFAULT 1.0,
        status TEXT DEFAULT 'planned', sort_order INTEGER DEFAULT 0,
        FOREIGN KEY (student_id) REFERENCES students (id))""")
    # migration: older DBs may lack the status/submitted_at columns
    cols = table_columns(conn, "log_entries")
    if "status" not in cols:
        conn.execute("ALTER TABLE log_entries ADD COLUMN status TEXT DEFAULT 'approved'")
    if "submitted_at" not in cols:
        conn.execute("ALTER TABLE log_entries ADD COLUMN submitted_at TEXT")
    if "struggled" not in cols:
        conn.execute("ALTER TABLE log_entries ADD COLUMN struggled INTEGER DEFAULT 0")
    if "block_start" not in cols:
        conn.execute("ALTER TABLE log_entries ADD COLUMN block_start TEXT")
    # migration: older DBs may lack newer health_habits columns
    cols = table_columns(conn, "health_habits")
    if "journal" not in cols:
        conn.execute("ALTER TABLE health_habits ADD COLUMN journal TEXT")
    if "day_rating" not in cols:
        conn.execute("ALTER TABLE health_habits ADD COLUMN day_rating INTEGER")
    if "mood_rating" not in cols:
        conn.execute("ALTER TABLE health_habits ADD COLUMN mood_rating INTEGER")
    # The old Yes/No "was today's lesson hard?" + "what was tough?" pair was
    # replaced by a 1-5 lesson_score (same scale as day/mood) plus one open
    # reflection field. Older DBs may still carry the lesson_hard columns;
    # they're simply left unread rather than dropped, since SQLite's DROP
    # COLUMN isn't available on every version this runs against.
    if "lesson_score" not in cols:
        conn.execute("ALTER TABLE health_habits ADD COLUMN lesson_score INTEGER")
    if "lesson_feedback" not in cols:
        conn.execute("ALTER TABLE health_habits ADD COLUMN lesson_feedback TEXT")
    # Tappable friction chips + which subject was roughest, replacing the open
    # text box as the primary "what went wrong" signal. day_rating is likewise
    # no longer collected — it and mood_rating were the same question to a
    # teenager, so mood_rating is now the single wellbeing read.
    if "friction_tags" not in cols:
        conn.execute("ALTER TABLE health_habits ADD COLUMN friction_tags TEXT")
    if "rough_subject" not in cols:
        conn.execute("ALTER TABLE health_habits ADD COLUMN rough_subject TEXT")
    if "daily_move" not in cols:
        conn.execute("ALTER TABLE health_habits ADD COLUMN daily_move INTEGER DEFAULT 0")
    # migration: class codes (ReadWorks, CommonLit, Kahoot etc. hand these out
    # when the parent creates a class; the student needs one to join, and it's
    # easy to lose track of otherwise)
    cols = table_columns(conn, "accounts")
    if "class_code" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN class_code TEXT")
    # migration: older DBs may lack the assignments photo_path/submitted_at columns
    cols = table_columns(conn, "assignments")
    if "photo_path" not in cols:
        conn.execute("ALTER TABLE assignments ADD COLUMN photo_path TEXT")
    if "submitted_at" not in cols:
        conn.execute("ALTER TABLE assignments ADD COLUMN submitted_at TEXT")
    # migration: older DBs may lack the travel_entries badge_earned/submitted_at
    # columns (present if this table used to be travel_journal, pre-consolidation)
    cols = table_columns(conn, "travel_entries")
    if "badge_earned" not in cols:
        conn.execute("ALTER TABLE travel_entries ADD COLUMN badge_earned INTEGER DEFAULT 0")
    if "submitted_at" not in cols:
        conn.execute("ALTER TABLE travel_entries ADD COLUMN submitted_at TEXT")
    # migration: older DBs may lack these newer per-table timestamp columns
    cols = table_columns(conn, "link_reports")
    if "submitted_at" not in cols:
        conn.execute("ALTER TABLE link_reports ADD COLUMN submitted_at TEXT")
    cols = table_columns(conn, "proposals")
    if "submitted_at" not in cols:
        conn.execute("ALTER TABLE proposals ADD COLUMN submitted_at TEXT")
    cols = table_columns(conn, "student_fun_projects")
    if "finished_at" not in cols:
        conn.execute("ALTER TABLE student_fun_projects ADD COLUMN finished_at TEXT")
    # migration: multi-subject projects that actually log hours (Quest Log redesign)
    cols = table_columns(conn, "fun_project_pool")
    if "subjects" not in cols:
        conn.execute("ALTER TABLE fun_project_pool ADD COLUMN subjects TEXT")
        conn.execute("UPDATE fun_project_pool SET subjects = subject WHERE subjects IS NULL")
    if "steps" not in cols:
        conn.execute("ALTER TABLE fun_project_pool ADD COLUMN steps TEXT")
    if "mess_level" not in cols:
        conn.execute("ALTER TABLE fun_project_pool ADD COLUMN mess_level TEXT DEFAULT 'Low'")
    if "est_hours" not in cols:
        conn.execute("ALTER TABLE fun_project_pool ADD COLUMN est_hours REAL DEFAULT 1.0")
    if "icon" not in cols:
        conn.execute("ALTER TABLE fun_project_pool ADD COLUMN icon TEXT DEFAULT '🗺️'")
    cols = table_columns(conn, "student_fun_projects")
    if "subjects" not in cols:
        conn.execute("ALTER TABLE student_fun_projects ADD COLUMN subjects TEXT")
        conn.execute("UPDATE student_fun_projects SET subjects = subject WHERE subjects IS NULL")
    if "steps" not in cols:
        conn.execute("ALTER TABLE student_fun_projects ADD COLUMN steps TEXT")
    if "est_hours" not in cols:
        conn.execute("ALTER TABLE student_fun_projects ADD COLUMN est_hours REAL DEFAULT 1.0")
    if "hours_logged" not in cols:
        conn.execute("ALTER TABLE student_fun_projects ADD COLUMN hours_logged INTEGER DEFAULT 0")
    if "icon" not in cols:
        conn.execute("ALTER TABLE student_fun_projects ADD COLUMN icon TEXT DEFAULT '🗺️'")
    cols = table_columns(conn, "student_books")
    if "finished_at" not in cols:
        conn.execute("ALTER TABLE student_books ADD COLUMN finished_at TEXT")
    cols = table_columns(conn, "curriculum_materials")
    if "seen" not in cols:
        conn.execute("ALTER TABLE curriculum_materials ADD COLUMN seen INTEGER DEFAULT 0")
    # migration: older DBs may lack these national_parks columns
    cols = table_columns(conn, "national_parks")
    if "booklet_url" not in cols:
        conn.execute("ALTER TABLE national_parks ADD COLUMN booklet_url TEXT")
    if "region" not in cols:
        conn.execute("ALTER TABLE national_parks ADD COLUMN region TEXT")
    # seed the elective, book, and fun-project pools once, on first run
    if conn.execute("SELECT COUNT(*) FROM elective_pool").fetchone()[0] == 0:
        for name, (resource_name, url, desc) in DEFAULT_ELECTIVE_POOL.items():
            conn.execute("""INSERT INTO elective_pool (name, resource_name, url, description)
                VALUES (?, ?, ?, ?)""", (name, resource_name, url, desc))
    if conn.execute("SELECT COUNT(*) FROM book_pool").fetchone()[0] == 0:
        for book in DEFAULT_BOOK_POOL:
            conn.execute("""INSERT INTO book_pool (title, author, ties_to, link)
                VALUES (?, ?, ?, ?)""",
                (book["title"], book["author"], book["ties_to"], book["link"]))
    if conn.execute("SELECT COUNT(*) FROM fun_project_pool").fetchone()[0] == 0:
        for proj in DEFAULT_FUN_PROJECTS:
            conn.execute("""INSERT INTO fun_project_pool (title, subject, description)
                VALUES (?, ?, ?)""",
                (proj["title"], proj["subject"], proj["description"]))
    # Quest Log starter projects, added incrementally (unlike the seed block
    # above, this runs every startup and only inserts titles not already
    # present) since fun_project_pool may already be populated from before.
    _existing_titles = {r[0] for r in
        conn.execute("SELECT title FROM fun_project_pool").fetchall()}
    for proj in LANDON_FUN_PROJECT_SEEDS:
        if proj["title"] not in _existing_titles:
            conn.execute("""INSERT INTO fun_project_pool
                (title, subjects, subject, description, steps, mess_level, est_hours, icon)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (proj["title"], proj["subjects"], proj["subjects"].split(",")[0].strip(),
                 proj["description"], proj["steps"], proj["mess_level"], proj["est_hours"],
                 proj["icon"]))
        else:
            # Row already existed from before the icon column was added —
            # backfill just the icon rather than skipping it entirely.
            conn.execute(
                "UPDATE fun_project_pool SET icon = ? WHERE title = ? AND icon = '🗺️'",
                (proj["icon"], proj["title"]))
    # Smithsonian collections: seeded exactly once, tracked by a settings flag
    # rather than by checking titles. Deliberate — a title check would silently
    # resurrect any collection the parent deleted on the next restart, and
    # these are suggestions, not fixtures.
    if not conn.execute("SELECT value FROM settings WHERE key = ?",
                        ("smithsonian_seeded",)).fetchone():
        for mat in SMITHSONIAN_LEARNING_LAB_SEEDS:
            conn.execute("""INSERT INTO curriculum_materials
                (title, subject, kind, url, notes, created_at)
                VALUES (?, ?, 'link', ?, ?, ?)""",
                (mat["title"], mat["subject"], mat["url"], mat["notes"],
                 datetime.now().isoformat(timespec="seconds")))
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                     ("smithsonian_seeded", "1"))
    # Foundations Track library: seeded once behind a flag (same reasoning as
    # the Smithsonian block) so a parent's edits and deletions stick.
    if not conn.execute("SELECT value FROM settings WHERE key = ?",
                        ("foundations_seeded",)).fetchone():
        for i, m in enumerate(FOUNDATIONS_MODULE_SEEDS):
            conn.execute("""INSERT INTO foundations_modules
                (title, pillar, description, objectives, activities, subjects,
                 est_hours, source_url, sort_order, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (m["title"], m["pillar"], m["description"], m["objectives"],
                 m["activities"], m["subjects"], m["est_hours"],
                 m["source_url"], i))
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                     ("foundations_seeded", "1"))
    if conn.execute("SELECT COUNT(*) FROM national_parks").fetchone()[0] == 0:
        for name, state, lat, lon, region in DEFAULT_NATIONAL_PARKS:
            conn.execute("""INSERT INTO national_parks (name, state, lat, lon, region)
                VALUES (?, ?, ?, ?, ?)""", (name, state, str(lat), str(lon), region))
    if conn.execute("SELECT COUNT(*) FROM major_cities").fetchone()[0] == 0:
        for name, state, lat, lon in DEFAULT_MAJOR_CITIES:
            conn.execute("""INSERT INTO major_cities (name, state, lat, lon)
                VALUES (?, ?, ?, ?)""", (name, state, str(lat), str(lon)))
    conn.commit()
    return conn


conn = get_conn()


def setting_get(key):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def setting_set(key, value):
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


def get_passion_profile(student_id):
    row = conn.execute("SELECT interests, core_values FROM passion_profile "
                       "WHERE student_id = ?", (student_id,)).fetchone()
    if not row:
        return {"interests": [], "core_values": ""}
    return {"interests": [t for t in (row[0] or "").split(",") if t],
            "core_values": row[1] or ""}


def set_passion_profile(student_id, interests, core_values):
    conn.execute("""INSERT INTO passion_profile
        (student_id, interests, core_values, updated_at) VALUES (?, ?, ?, ?)
        ON CONFLICT(student_id) DO UPDATE SET interests = excluded.interests,
        core_values = excluded.core_values, updated_at = excluded.updated_at""",
        (student_id, ",".join(interests), core_values,
         datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def get_students():
    return pd.read_sql("SELECT * FROM students ORDER BY name", conn)


def get_entries(student_id, statuses=None):
    df = pd.read_sql("SELECT * FROM log_entries WHERE student_id = ? "
                     "ORDER BY entry_date DESC, id DESC", conn, params=[student_id])
    if statuses:
        df = df[df["status"].isin(statuses)]
    return df


def add_entry(student_id, entry_date, subject, hours, description, day_type, status,
              struggled=False, block_start=None):
    conn.execute("""INSERT INTO log_entries
        (student_id, entry_date, subject, hours, description, day_type, status,
         submitted_at, struggled, block_start)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (student_id, entry_date.isoformat(), subject, hours, description, day_type,
         status, datetime.now().isoformat(timespec="seconds"), int(struggled),
         block_start))
    conn.commit()


def get_block_entry(student_id, d, subject, start=None):
    """The full log_entries row for one schedule block, or None if not logged yet.

    Matches on block_start when given, so two blocks that share a subject on
    the same day (e.g. the main Mathematics block and a separate IXL block)
    track independently. Rows with no block_start (logged before this field
    existed, or added via Manual Log) still match by date+subject alone —
    there was never more than one block per subject/day before this."""
    df = get_entries(student_id)
    if df.empty:
        return None
    m = df[(df["entry_date"] == d.isoformat()) & (df["subject"] == subject)]
    if start is not None:
        m = m[(m["block_start"] == start) | (m["block_start"].isna())]
    return None if m.empty else m.iloc[0]


def update_entry_status(entry_id, status, hours=None):
    if hours is not None:
        conn.execute("UPDATE log_entries SET status = ?, hours = ? WHERE id = ?",
                     (status, hours, entry_id))
    else:
        conn.execute("UPDATE log_entries SET status = ? WHERE id = ?", (status, entry_id))
    conn.commit()


def delete_entry(entry_id):
    conn.execute("DELETE FROM log_entries WHERE id = ?", (entry_id,))
    conn.commit()


def get_assignments(student_id):
    return pd.read_sql("SELECT * FROM assignments WHERE student_id = ? "
                       "ORDER BY assign_date DESC, id DESC", conn, params=[student_id])


def add_assignment(student_id, a_date, subject, title, score, max_score, notes,
                    photo_path=None):
    conn.execute("""INSERT INTO assignments
        (student_id, assign_date, subject, title, score, max_score, notes, photo_path,
         submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (student_id, a_date.isoformat(), subject, title, score, max_score, notes,
         photo_path, datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def delete_assignment(assign_id):
    row = conn.execute("SELECT photo_path FROM assignments WHERE id = ?",
                       (assign_id,)).fetchone()
    if row and row[0]:
        photo_full_path = Path(__file__).parent / row[0]
        if photo_full_path.exists():
            photo_full_path.unlink()
    conn.execute("DELETE FROM assignments WHERE id = ?", (assign_id,))
    conn.commit()


def get_assessments(student_id):
    return pd.read_sql("SELECT * FROM assessments WHERE student_id = ? "
                       "ORDER BY assessment_date DESC", conn, params=[student_id])


def add_assessment(student_id, a_date, a_type, evaluator, result, notes):
    conn.execute("""INSERT INTO assessments
        (student_id, assessment_date, assessment_type, evaluator, result, notes)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (student_id, a_date.isoformat(), a_type, evaluator, result, notes))
    conn.commit()


def get_assessment_reminder(student_id, school_year):
    """(level, message) if the annual assessment needs attention, else None.
    level: 'error' (overdue), 'warning' (<=60 days left), 'info' (<=120 days left)."""
    start_d, end_d = get_school_year_dates(school_year)
    if not end_d:
        return None  # can't judge urgency without a school year end date

    hist = get_assessments(student_id)
    if not hist.empty:
        window_start = (start_d or date(end_d.year - 1, 1, 1)).isoformat()
        done_this_year = hist[(hist["assessment_date"] >= window_start)
                              & (hist["assessment_date"] <= end_d.isoformat())]
        if not done_this_year.empty:
            return None  # already done for this school year

    days_left = (end_d - date.today()).days
    if days_left < 0:
        return ("error", f"⚠️ **Annual assessment overdue** — the school year "
                f"end date ({fmt_date(end_d)}) has passed and "
                "none is on record. WA law (RCW 28A.200.010) requires one "
                "every year. See the ✅ Assessments tab.")
    if days_left <= 60:
        return ("warning", f"📋 **Annual assessment reminder** — {days_left} "
                "day(s) left in the school year and nothing recorded yet. "
                "See the ✅ Assessments tab for how to schedule one.")
    if days_left <= 120:
        return ("info", f"📋 Annual assessment not recorded yet — "
                f"{days_left} days left in the school year. Plenty of time, "
                "but worth planning. See the ✅ Assessments tab.")
    return None


# WA RCW 28A.200.010 requires the Declaration of Intent to be filed by
# Sept 15 (or within 2 weeks of the term start) EVERY school year — so
# the dismiss flag is keyed per school_year, not a one-time-ever flag.
DOI_QUALIFICATION_OPTIONS = [
    "Supervised by a certificated person for at least 45 school days "
    "pursuant to a home-based instruction program.",
    "Completed a course in home-based instruction at a post-secondary "
    "institution or vocational-technical school.",
    "Advised by a school psychologist regarding home-based study prior "
    "to starting the program.",
    "Hold a bachelor's degree.",
    "Deemed qualified by the superintendent of the district.",
    "Instructed within a public or private school for at least the "
    "equivalent of two full school years within the last four years.",
]


def doi_letter_template(student_name, school_year):
    options = "\n".join(f"- ( ) {opt}" for opt in DOI_QUALIFICATION_OPTIONS)
    return f"""Subject: Declaration of Intent to Provide Home-Based Instruction — {student_name or "[Student's Full Name]"}

To the [District Name] School District,

This letter serves as my Declaration of Intent to provide home-based instruction to my child for the {school_year} school year, pursuant to RCW 28A.200.010.

Student: {student_name or "[Student's full legal name]"}
Date of birth: [MM/DD/YYYY]
Address: [home address]
Grade level: [grade]
Parent/guardian: [your full name]

I meet the qualification requirements of RCW 28A.200.010(4) under the following provision (keep one):

{options}

Please confirm receipt of this declaration at your convenience.

Sincerely,
[Your name]
[Phone / email]"""


def get_doi_reminder(school_year):
    """(level, days_left, deadline) for the WA Declaration of Intent
    deadline, or None if already dismissed for this school year."""
    if setting_get(f"doi_dismissed_{school_year}") == "1":
        return None
    today = date.today()
    deadline = date(today.year, 9, 15)
    if today > deadline:
        deadline = date(today.year + 1, 9, 15)
    days_left = (deadline - today).days
    if days_left <= 0:
        level = "error"
    elif days_left <= 14:
        level = "warning"
    else:
        level = "info"
    return (level, days_left, deadline)


def get_parent_checkins(student_id):
    return pd.read_sql("SELECT * FROM parent_checkins WHERE student_id = ? "
                       "ORDER BY checkin_date DESC", conn, params=[student_id])


def add_parent_checkin(student_id, checkin_date, notes):
    conn.execute("""INSERT INTO parent_checkins (student_id, checkin_date, notes)
        VALUES (?, ?, ?)""", (student_id, checkin_date.isoformat(), notes))
    conn.commit()


def delete_parent_checkin(checkin_id):
    conn.execute("DELETE FROM parent_checkins WHERE id = ?", (checkin_id,))
    conn.commit()


def get_checkin_reminder(student_id):
    """Gentle nudge if it's been 14+ days (or never) since the last logged check-in."""
    hist = get_parent_checkins(student_id)
    if hist.empty:
        return "You haven't logged a check-in yet — a quick conversation " \
               "and a note here can be worth a lot over time."
    last = date.fromisoformat(hist.iloc[0]["checkin_date"])
    days_since = (date.today() - last).days
    if days_since >= 14:
        return (f"It's been {days_since} days since your last logged "
                "check-in — might be worth a quick conversation about how "
                "he's doing.")
    return None


def get_elective_pool_df():
    return pd.read_sql("SELECT * FROM elective_pool ORDER BY name", conn)


def get_elective_pool_dict():
    df = get_elective_pool_df()
    return {r["name"]: (r["resource_name"], r["url"], r["description"])
            for _, r in df.iterrows()}


def add_elective_pool_option(name, resource_name, url, description):
    conn.execute("""INSERT INTO elective_pool (name, resource_name, url, description)
        VALUES (?, ?, ?, ?)""", (name, resource_name, url, description))
    conn.commit()


def update_elective_pool_option(option_id, name, resource_name, url, description):
    conn.execute("""UPDATE elective_pool SET name = ?, resource_name = ?, url = ?,
        description = ? WHERE id = ?""", (name, resource_name, url, description, option_id))
    conn.commit()


def delete_elective_pool_option(option_id):
    conn.execute("DELETE FROM elective_pool WHERE id = ?", (option_id,))
    conn.commit()


def get_book_pool_df():
    return pd.read_sql("SELECT * FROM book_pool ORDER BY title", conn)


def add_book_pool_option(title, author, ties_to, link):
    conn.execute("""INSERT INTO book_pool (title, author, ties_to, link)
        VALUES (?, ?, ?, ?)""", (title, author, ties_to, link))
    conn.commit()


def update_book_pool_option(option_id, title, author, ties_to, link):
    conn.execute("""UPDATE book_pool SET title = ?, author = ?, ties_to = ?,
        link = ? WHERE id = ?""", (title, author, ties_to, link, option_id))
    conn.commit()


def delete_book_pool_option(option_id):
    conn.execute("DELETE FROM book_pool WHERE id = ?", (option_id,))
    conn.commit()


def get_fun_project_pool_df():
    return pd.read_sql("SELECT * FROM fun_project_pool ORDER BY subject, title", conn)


def add_fun_project_pool_option(title, subjects, description, steps, mess_level, est_hours,
                                 icon):
    try:
        est_hours = float(est_hours)
    except (TypeError, ValueError):
        est_hours = 1.0
    conn.execute("""INSERT INTO fun_project_pool
        (title, subjects, subject, description, steps, mess_level, est_hours, icon)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, subjects, (subjects or "").split(",")[0].strip(),
         description, steps, mess_level or "Low", est_hours, icon or "🗺️"))
    conn.commit()


def update_fun_project_pool_option(option_id, title, subjects, description, steps,
                                    mess_level, est_hours, icon):
    try:
        est_hours = float(est_hours)
    except (TypeError, ValueError):
        est_hours = 1.0
    conn.execute("""UPDATE fun_project_pool SET title = ?, subjects = ?, subject = ?,
        description = ?, steps = ?, mess_level = ?, est_hours = ?, icon = ? WHERE id = ?""",
        (title, subjects, (subjects or "").split(",")[0].strip(),
         description, steps, mess_level or "Low", est_hours, icon or "🗺️", option_id))
    conn.commit()


def delete_fun_project_pool_option(option_id):
    conn.execute("DELETE FROM fun_project_pool WHERE id = ?", (option_id,))
    conn.commit()


def save_uploaded_curriculum_file(uploaded_file):
    """Write an st.file_uploader result to uploads/curriculum, return its
    path relative to the app folder (what gets stored in the DB)."""
    target_dir = UPLOADS_BASE / "curriculum"
    target_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(uploaded_file.name).suffix or ".dat"
    fname = f"{int(time.time() * 1000)}{ext}"
    (target_dir / fname).write_bytes(uploaded_file.getvalue())
    return str(Path("uploads") / "curriculum" / fname)


def get_curriculum_materials():
    return pd.read_sql(
        "SELECT * FROM curriculum_materials ORDER BY subject, created_at DESC", conn)


def add_curriculum_material(title, subject, kind, file_path, url, notes):
    conn.execute("""INSERT INTO curriculum_materials
        (title, subject, kind, file_path, url, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (title, subject, kind, file_path, url, notes, datetime.now().isoformat()))
    conn.commit()


def delete_curriculum_material(material_id):
    conn.execute("DELETE FROM curriculum_materials WHERE id = ?", (material_id,))
    conn.commit()


def mark_curriculum_materials_seen():
    conn.execute("UPDATE curriculum_materials SET seen = 1 WHERE seen = 0 OR seen IS NULL")
    conn.commit()


def get_national_parks_df():
    return pd.read_sql("SELECT * FROM national_parks ORDER BY name", conn)


def add_national_park(name, state, lat, lon, booklet_url="", region=""):
    conn.execute("""INSERT INTO national_parks
        (name, state, lat, lon, booklet_url, region)
        VALUES (?, ?, ?, ?, ?, ?)""", (name, state, lat, lon, booklet_url, region))
    conn.commit()


def update_national_park(park_id, name, state, lat, lon, booklet_url="", region=""):
    conn.execute("""UPDATE national_parks SET name = ?, state = ?, lat = ?,
        lon = ?, booklet_url = ?, region = ? WHERE id = ?""",
        (name, state, lat, lon, booklet_url, region, park_id))
    conn.commit()


def delete_national_park(park_id):
    conn.execute("DELETE FROM national_parks WHERE id = ?", (park_id,))
    conn.commit()


def get_major_cities_df():
    return pd.read_sql("SELECT * FROM major_cities ORDER BY name", conn)


def add_major_city(name, state, lat, lon):
    conn.execute("""INSERT INTO major_cities (name, state, lat, lon)
        VALUES (?, ?, ?, ?)""", (name, state, lat, lon))
    conn.commit()


def update_major_city(city_id, name, state, lat, lon):
    conn.execute("""UPDATE major_cities SET name = ?, state = ?, lat = ?,
        lon = ? WHERE id = ?""", (name, state, lat, lon, city_id))
    conn.commit()


def delete_major_city(city_id):
    conn.execute("DELETE FROM major_cities WHERE id = ?", (city_id,))
    conn.commit()


def save_uploaded_photo(uploaded_file, student_id, subdir="journal"):
    """Write an st.file_uploader result to disk, return its path relative to
    the app folder (what gets stored in the DB)."""
    target_dir = UPLOADS_BASE / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(uploaded_file.name).suffix or ".jpg"
    fname = f"{student_id}_{int(time.time() * 1000)}{ext}"
    (target_dir / fname).write_bytes(uploaded_file.getvalue())
    return str(Path("uploads") / subdir / fname)


def get_travel_entries(student_id):
    """Every travel entry — park visit, state visit, city visit, or freeform
    journal entry are all just entries with different tags set."""
    return pd.read_sql("""SELECT e.*,
        p.name AS park_name, p.state AS park_state, p.region AS park_region,
        p.lat AS park_lat, p.lon AS park_lon, p.booklet_url AS park_booklet_url,
        c.name AS city_name, c.state AS city_state, c.lat AS city_lat, c.lon AS city_lon
        FROM travel_entries e
        LEFT JOIN national_parks p ON e.tag_park_id = p.id
        LEFT JOIN major_cities c ON e.tag_city_id = c.id
        WHERE e.student_id = ? ORDER BY e.entry_date DESC, e.id DESC""",
        conn, params=[student_id])


def add_travel_entry(student_id, school_year, entry_date, title, content,
                     photo_path, tag_state, tag_park_id, tag_city_id,
                     badge_earned=False):
    conn.execute("""INSERT INTO travel_entries
        (student_id, school_year, entry_date, title, content, photo_path,
         tag_state, tag_park_id, tag_city_id, badge_earned, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (student_id, school_year, entry_date.isoformat(), title, content,
         photo_path, tag_state, tag_park_id, tag_city_id, int(badge_earned),
         datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def delete_travel_entry(entry_id):
    row = conn.execute("SELECT photo_path FROM travel_entries WHERE id = ?",
                       (entry_id,)).fetchone()
    if row and row[0]:
        (Path(__file__).parent / row[0]).unlink(missing_ok=True)
    conn.execute("DELETE FROM travel_entries WHERE id = ?", (entry_id,))
    conn.commit()


def get_all_visited_states(student_id):
    """States visited — union of directly-tagged states, park-visit states,
    and city-visit states across all travel entries."""
    entries = get_travel_entries(student_id)
    if entries.empty:
        return set()
    visited = set(entries["tag_state"].dropna())
    visited |= set(entries["park_state"].dropna())
    visited |= set(entries["city_state"].dropna())
    return visited


def get_link_reports(student_id, status=None):
    q = "SELECT * FROM link_reports WHERE student_id = ?"
    params = [student_id]
    if status:
        q += " AND status = ?"
        params.append(status)
    q += " ORDER BY report_date DESC"
    return pd.read_sql(q, conn, params=params)


def add_link_report(student_id, url, description):
    conn.execute("""INSERT INTO link_reports
        (student_id, report_date, url, description, status, submitted_at)
        VALUES (?, ?, ?, ?, 'pending', ?)""",
        (student_id, date.today().isoformat(), url, description,
         datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def update_link_report(report_id, status, parent_note=""):
    resolved = date.today().isoformat() if status != "pending" else None
    conn.execute("""UPDATE link_reports SET status = ?, parent_note = ?,
        resolved_date = ? WHERE id = ?""",
        (status, parent_note, resolved, report_id))
    conn.commit()


def delete_link_report(report_id):
    conn.execute("DELETE FROM link_reports WHERE id = ?", (report_id,))
    conn.commit()


def get_student_fun_projects(student_id, school_year):
    return pd.read_sql("SELECT * FROM student_fun_projects WHERE student_id = ? "
                       "AND school_year = ? ORDER BY id", conn,
                       params=[student_id, school_year])


def add_student_fun_project(student_id, school_year, title, subjects, description,
                             steps=None, est_hours=1.0, icon="🗺️"):
    conn.execute("""INSERT INTO student_fun_projects
        (student_id, school_year, title, subject, subjects, description, steps,
         est_hours, icon, status, selected_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned', ?)""",
        (student_id, school_year, title, (subjects or "").split(",")[0].strip(),
         subjects, description, steps, est_hours, icon or "🗺️",
         date.today().isoformat()))
    conn.commit()


def update_fun_project_status(project_id, status):
    """For planned <-> in_progress transitions only. Use finish_fun_project()
    when the new status is "finished" — that path also logs hours."""
    conn.execute("UPDATE student_fun_projects SET status = ? WHERE id = ?",
                 (status, project_id))
    conn.commit()


def parse_steps(steps_text):
    return [s.strip() for s in (steps_text or "").split("\n") if s.strip()]


def mess_badge(mess_level):
    return {"Low": "🧼 Low mess", "Medium": "🧽 Medium mess",
           "High": "💦 High mess"}.get(mess_level, "🧼 Low mess")


# Trading-card styling for the Quest Board — a deliberately fixed bright
# card face (like a real physical card) rather than following Streamlit's
# light/dark theme, same way a paper card doesn't change color in the dark.
# Comic Log — the app's visual identity: thick ink borders, halftone-dot
# panel shading, hand-laid-page tilt, punchy varied pop-art colors rather
# than a single muted accent. QUEST_POP_COLORS rotates across queued cards
# so the board reads as colorful panels, not a monochrome list.
QUEST_POP_COLORS = ["#FFD23F", "#4FC3E8", "#FF5FA2", "#6FCF7A", "#B084F0", "#FF9F45"]

QUEST_CARD_CSS = """
<style>
.qcard { border: 3px solid #1A1610; border-radius: 7px; overflow: hidden; margin-bottom: 18px;
  background: #FFFDF6; box-shadow: 4px 4px 0 #1A1610; transition: transform 0.15s ease; }
.qcard:hover { transform: translate(-2px, -2px); box-shadow: 6px 6px 0 #1A1610; }
.qcard-art { height: 88px; display: flex; align-items: center; justify-content: center;
  font-size: 40px; position: relative; border-bottom: 3px solid #1A1610;
  background-image: repeating-radial-gradient(circle, #1A161055 0 1.5px, transparent 1.5px 7px); }
.qcard-ribbon { position: absolute; top: 6px; left: 6px; font-size: 9px; font-weight: 800;
  letter-spacing: 0.05em; text-transform: uppercase; padding: 3px 8px; border-radius: 10px;
  background: #FFFDF6; border: 2px solid #1A1610; color: #1A1610; }
.qcard-body { padding: 10px 13px 12px; }
.qcard-title { font-weight: 800; font-size: 14.5px; margin-bottom: 3px; color: #1A1610; }
.qcard-tags { font-size: 10.5px; color: #6b6152; margin-bottom: 6px; }
.qcard-desc { font-size: 11.5px; color: #3a352c; line-height: 1.4; margin-bottom: 8px; }
.qcard-stats { display: flex; justify-content: space-between; align-items: center;
  border-top: 2px dashed #1A161044; padding-top: 6px; font-size: 10.5px; }
.qcard-hours { font-weight: 800; color: #1A1610; }
.qcard-mess i { width: 5px; height: 5px; border-radius: 50%; display: inline-block;
  margin-left: 2px; background: #1A161022; }
.qcard-mess i.on { background: #E8402C; }

/* Sprint board — Today and My Week render as columns of cards rather than a
   vertical list. Same ink-border/pop-color language as the quest cards, but
   compact enough that a whole day (or week) fits on one screen: the point is
   seeing work *move* from To Do to Done, which a list can't show. */
.slane { border: 3px solid #1A1610; border-radius: 8px; background: #FFFDF6cc;
  padding: 8px; min-height: 60px; box-shadow: 3px 3px 0 #1A1610; }
.slane-head { font-weight: 900; font-size: 12px; letter-spacing: .06em;
  text-transform: uppercase; color: #1A1610; padding: 3px 8px; margin-bottom: 8px;
  border: 2px solid #1A1610; border-radius: 20px; display: inline-block;
  background: #FFD23F; }
.slane-head.done { background: #6FCF7A; }
.slane-head.today { background: #FF5FA2; }
.bcard { border: 3px solid #1A1610; border-radius: 6px; background: #FFFDF6;
  box-shadow: 2px 2px 0 #1A1610; margin-bottom: 8px; overflow: hidden;
  transition: transform .12s ease; }
.bcard:hover { transform: translate(-1px, -1px); box-shadow: 3px 3px 0 #1A1610; }
.bcard-strip { height: 7px; border-bottom: 2px solid #1A1610; }
.bcard-in { padding: 7px 9px 8px; }
.bcard-t { font-weight: 800; font-size: 13px; color: #1A1610; line-height: 1.25; }
.bcard-when { font-size: 10px; color: #6b6152; font-weight: 700; }
.bcard-badge { font-size: 10px; font-weight: 800; }
.bcard.is-done { opacity: .62; }
.bcard.is-done .bcard-t { text-decoration: line-through; }
</style>
"""


def render_quest_card(p, status):
    """Render one quest as a Comic Log panel: thick ink border, halftone
    art background, hand-laid tilt, speech-bubble ribbon. status is
    'queued', 'active', or 'done' — controls the ribbon text and art
    color. Purely visual; the caller renders real st.button()s beneath
    since HTML inside st.markdown can't call back into Python."""
    ribbon = {"queued": "New!", "active": "In Progress", "done": "The End"}[status]
    icon = p["icon"] or "🗺️"
    title = escape_html(str(p["title"]))
    tags = escape_html(str(p["subjects"] or p["subject"] or ""))
    desc = escape_html(str(p["description"] or ""))
    hours = p["est_hours"] or 1.0
    mess_level = p["mess_level"] if "mess_level" in p.index else "Low"
    mess_n = {"Low": 1, "Medium": 2, "High": 3}.get(mess_level, 1)
    dots = "".join(f'<i class="{"on" if n <= mess_n else ""}"></i>' for n in (1, 2, 3))
    if status == "active":
        art_color = "#FF9F45"
    elif status == "done":
        art_color = "#FFD23F"
    else:
        art_color = QUEST_POP_COLORS[int(p["id"]) % len(QUEST_POP_COLORS)]
    rotation = -0.6 if int(p["id"]) % 2 == 0 else 0.6
    st.markdown(f"""
        <div class="qcard" style="transform:rotate({rotation}deg);background-color:{art_color}00">
          <div class="qcard-art" style="background-color:{art_color}">{icon}
            <div class="qcard-ribbon">{ribbon}</div></div>
          <div class="qcard-body">
            <div class="qcard-title">{title}</div>
            <div class="qcard-tags">{tags}</div>
            <div class="qcard-desc">{desc}</div>
            <div class="qcard-stats">
              <span class="qcard-hours">{hours:.1f} HRS</span>
              <span class="qcard-mess">{dots}</span>
            </div>
          </div>
        </div>
    """, unsafe_allow_html=True)


def render_block_card(subject, start=None, end=None, status=None, struggled=False):
    """One schedule block as a small board card. Visual only — the caller adds
    the real st.button()s beneath, same arrangement as render_quest_card."""
    color = QUEST_SUBJECT_COLORS.get(subject, "#FFD23F")
    title = escape_html(QUEST_TITLES.get(subject, subject))
    when = (f"{format_time12(start)} – {format_time12(end)}"
            if start and end else "")
    badge = {"pending": "🕓 waiting on parent", "approved": "✅ approved",
             "rejected": "❌ sent back"}.get(status, "")
    if struggled:
        badge += " · 😕"
    done_cls = " is-done" if status in ("pending", "approved") else ""
    st.markdown(f"""
        <div class="bcard{done_cls}">
          <div class="bcard-strip" style="background:{color}"></div>
          <div class="bcard-in">
            <div class="bcard-t">{title}</div>
            <div class="bcard-when">{when}</div>
            <div class="bcard-badge">{badge}</div>
          </div>
        </div>
    """, unsafe_allow_html=True)


def finish_fun_project(project_id, student_id, title, subjects_str, est_hours):
    """Marks a student_fun_projects row finished and — once, idempotently —
    splits est_hours evenly across its valid tagged WA subjects into pending
    log_entries rows for parent approval, same as any schedule-block entry.
    Falls back to "Occupational Education" if every tag is invalid (e.g. a
    typo), so hours are never silently dropped from the compliance total."""
    row = conn.execute("SELECT hours_logged FROM student_fun_projects WHERE id = ?",
                       (project_id,)).fetchone()
    already_logged = bool(row and row[0])
    finished = date.today().isoformat()
    finished_at = datetime.now().isoformat(timespec="seconds")
    conn.execute("""UPDATE student_fun_projects
        SET status = 'finished', finished_date = ?, finished_at = ? WHERE id = ?""",
        (finished, finished_at, project_id))
    if not already_logged:
        valid = [s.strip() for s in (subjects_str or "").split(",")
                if s.strip() in WA_SUBJECTS + ["Electives"]]
        if not valid:
            valid = ["Occupational Education"]
        try:
            est_hours = float(est_hours)
        except (TypeError, ValueError):
            est_hours = 1.0
        per_subject = round(est_hours / len(valid), 2)
        for subj in valid:
            add_entry(student_id, date.today(), subj, per_subject,
                     f"Finished fun project: {title}", "Instruction", "pending",
                     struggled=False, block_start=None)
        conn.execute("UPDATE student_fun_projects SET hours_logged = 1 WHERE id = ?",
                    (project_id,))
    conn.commit()


def delete_student_fun_project(project_id):
    conn.execute("DELETE FROM student_fun_projects WHERE id = ?", (project_id,))
    conn.commit()


# ----- Foundations Track -----
def get_foundations_modules_df(active_only=True):
    q = "SELECT * FROM foundations_modules"
    if active_only:
        q += " WHERE active = 1"
    q += " ORDER BY sort_order, pillar, title"
    return pd.read_sql(q, conn)


def add_foundations_module(title, pillar, description, objectives, activities,
                            subjects, est_hours, source_url):
    try:
        est_hours = float(est_hours)
    except (TypeError, ValueError):
        est_hours = 1.0
    nxt = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 "
                       "FROM foundations_modules").fetchone()[0]
    conn.execute("""INSERT INTO foundations_modules
        (title, pillar, description, objectives, activities, subjects, est_hours,
         source_url, sort_order, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (title, pillar, description, objectives, activities, subjects, est_hours,
         source_url, nxt))
    conn.commit()


def update_foundations_module(module_id, title, pillar, description, objectives,
                               activities, subjects, est_hours, source_url):
    try:
        est_hours = float(est_hours)
    except (TypeError, ValueError):
        est_hours = 1.0
    conn.execute("""UPDATE foundations_modules SET title = ?, pillar = ?,
        description = ?, objectives = ?, activities = ?, subjects = ?,
        est_hours = ?, source_url = ? WHERE id = ?""",
        (title, pillar, description, objectives, activities, subjects, est_hours,
         source_url, module_id))
    conn.commit()


def delete_foundations_module(module_id):
    """Hard-delete the module plus any student progress rows pointing at it —
    no ON DELETE CASCADE in this schema, so clean up here."""
    conn.execute("DELETE FROM student_foundations_progress WHERE module_id = ?",
                (module_id,))
    conn.execute("DELETE FROM foundations_modules WHERE id = ?", (module_id,))
    conn.commit()


def get_student_foundations(student_id):
    """Every module joined to this student's progress (status/completed_at).
    Modules with no progress row yet come back with NULLs."""
    return pd.read_sql("""SELECT m.*, p.status AS prog_status,
        p.completed_at, p.hours_logged
        FROM foundations_modules m
        LEFT JOIN student_foundations_progress p
          ON p.module_id = m.id AND p.student_id = ?
        WHERE m.active = 1
        ORDER BY m.sort_order, m.pillar, m.title""", conn, params=[student_id])


def complete_foundations_module(module_id, student_id, title, subjects_str,
                                 est_hours):
    """Mark a Foundations module complete and — once, idempotently — split
    est_hours across its tagged WA subjects into pending log_entries, exactly
    like finish_fun_project does for a quest."""
    row = conn.execute("""SELECT hours_logged FROM student_foundations_progress
        WHERE student_id = ? AND module_id = ?""",
        (student_id, module_id)).fetchone()
    already_logged = bool(row and row[0])
    completed_at = datetime.now().isoformat(timespec="seconds")
    if row:
        conn.execute("""UPDATE student_foundations_progress
            SET status = 'complete', completed_at = ?
            WHERE student_id = ? AND module_id = ?""",
            (completed_at, student_id, module_id))
    else:
        conn.execute("""INSERT INTO student_foundations_progress
            (student_id, module_id, status, completed_at, hours_logged)
            VALUES (?, ?, 'complete', ?, 0)""",
            (student_id, module_id, completed_at))
    if not already_logged:
        valid = [s.strip() for s in (subjects_str or "").split(",")
                if s.strip() in WA_SUBJECTS + ["Electives"]]
        if not valid:
            valid = ["Occupational Education"]
        try:
            est_hours = float(est_hours)
        except (TypeError, ValueError):
            est_hours = 1.0
        per_subject = round(est_hours / len(valid), 2)
        for subj in valid:
            add_entry(student_id, date.today(), subj, per_subject,
                     f"Foundations: {title}", "Instruction", "pending",
                     struggled=False, block_start=None)
        conn.execute("""UPDATE student_foundations_progress SET hours_logged = 1
            WHERE student_id = ? AND module_id = ?""", (student_id, module_id))
    conn.commit()


def reopen_foundations_module(module_id, student_id):
    """Undo a completion (leaves any already-logged hours in place — those are
    the parent's to reject in Review & Approve, same as an un-finished quest)."""
    conn.execute("""UPDATE student_foundations_progress
        SET status = 'in_progress', completed_at = NULL
        WHERE student_id = ? AND module_id = ?""", (student_id, module_id))
    conn.commit()


# ----- Weekly Plan Blender (the defining Compass mechanic) -----
DEFAULT_BLEND_RATIO = 60       # % of the plan that is Passion (rest Foundations)
DEFAULT_WEEKLY_TARGET = 6.0    # project hours/week the blender plans for


def get_blend_settings(student_id):
    ratio = setting_get(f"blend_ratio_{student_id}")
    target = setting_get(f"weekly_hours_target_{student_id}")
    return {"ratio": int(ratio) if ratio else DEFAULT_BLEND_RATIO,
            "target": float(target) if target else DEFAULT_WEEKLY_TARGET}


def set_blend_settings(student_id, ratio, target):
    setting_set(f"blend_ratio_{student_id}", str(int(ratio)))
    setting_set(f"weekly_hours_target_{student_id}", str(float(target)))


def _monday_of(d):
    return d - timedelta(days=d.weekday())


def _interest_keywords(profile):
    """Bare keywords from the interest chips (emoji + connectors stripped),
    for loosely ranking which pool quests match what he's into."""
    words = set()
    for chip in profile.get("interests", []):
        txt = chip.split(" ", 1)[1] if " " in chip else chip
        for w in re.split(r"[^a-z]+", txt.lower()):
            if len(w) > 2 and w not in ("and", "the"):
                words.add(w)
    return words


def _quest_interest_score(row, kw):
    if not kw:
        return 0
    hay = " ".join(str(row.get(c, "") or "") for c in
                   ("title", "subjects", "subject", "description")).lower()
    return sum(1 for w in kw if w in hay)


def get_weekly_plan(student_id, week_start):
    monday = _monday_of(week_start)
    return pd.read_sql("""SELECT * FROM weekly_plan_items
        WHERE student_id = ? AND week_start = ? ORDER BY sort_order""",
        conn, params=[student_id, monday.isoformat()])


def generate_weekly_plan(student_id, school_year, week_start):
    """Build one blended week from the ratio + target: fill ~ratio% of the
    hours with Passion quests (his queued ones first, then interest-matched
    pool quests auto-added as quests) and the rest with not-yet-done
    Foundations modules, interleaved into a single list. Completed items from
    an earlier generation of the same week are kept and count toward the
    targets; only the unfinished ones are regenerated."""
    monday = _monday_of(week_start)
    s = get_blend_settings(student_id)
    passion_target = s["target"] * s["ratio"] / 100.0
    found_target = s["target"] - passion_target

    existing = get_weekly_plan(student_id, monday)
    done = existing[existing["status"] == "done"] if not existing.empty else existing
    done_passion_h = done[done["kind"] == "passion"]["est_hours"].sum() if not done.empty else 0.0
    done_found_h = done[done["kind"] == "foundations"]["est_hours"].sum() if not done.empty else 0.0
    done_refs = {(r["kind"], r["ref_id"]) for _, r in done.iterrows()} if not done.empty else set()

    # wipe the not-done items; we're about to rebuild them
    conn.execute("""DELETE FROM weekly_plan_items
        WHERE student_id = ? AND week_start = ? AND status != 'done'""",
        (student_id, monday.isoformat()))

    profile = get_passion_profile(student_id)
    kw = _interest_keywords(profile)

    # ---- passion candidates: his own queued/in-progress quests first
    passion = []
    mine = get_student_fun_projects(student_id, school_year)
    if not mine.empty:
        act = mine[mine["status"].isin(["planned", "in_progress"])]
        act = act.assign(_score=[_quest_interest_score(r, kw) for _, r in act.iterrows()])
        for _, r in act.sort_values("_score", ascending=False).iterrows():
            if ("passion", int(r["id"])) in done_refs:
                continue
            passion.append({"ref_id": int(r["id"]), "title": r["title"],
                            "subjects": r["subjects"] or r["subject"],
                            "est_hours": float(r["est_hours"] or 1.0)})
    # ---- top up from the pool (interest-ranked), auto-adding as his quests
    have = passion_target - done_passion_h - sum(p["est_hours"] for p in passion)
    if have > 0:
        pool = get_fun_project_pool_df()
        mine_titles = set(mine["title"]) if not mine.empty else set()
        pool = pool[~pool["title"].isin(mine_titles)]
        pool = pool.assign(_score=[_quest_interest_score(r, kw) for _, r in pool.iterrows()])
        for _, r in pool.sort_values("_score", ascending=False).iterrows():
            if have <= 0:
                break
            add_student_fun_project(student_id, school_year, r["title"],
                                    r["subjects"] or r["subject"], r["description"],
                                    r["steps"], r["est_hours"] or 1.0, r["icon"])
            new_id = conn.execute("""SELECT id FROM student_fun_projects
                WHERE student_id = ? AND title = ? ORDER BY id DESC LIMIT 1""",
                (student_id, r["title"])).fetchone()[0]
            eh = float(r["est_hours"] or 1.0)
            passion.append({"ref_id": int(new_id), "title": r["title"],
                            "subjects": r["subjects"] or r["subject"], "est_hours": eh})
            have -= eh

    # ---- foundations candidates: incomplete modules in order
    foundations = []
    sf = get_student_foundations(student_id)
    if not sf.empty:
        todo = sf[sf["prog_status"] != "complete"]
        acc = found_target - done_found_h
        for _, r in todo.iterrows():
            if acc <= 0:
                break
            if ("foundations", int(r["id"])) in done_refs:
                continue
            eh = float(r["est_hours"] or 1.0)
            foundations.append({"ref_id": int(r["id"]), "title": r["title"],
                                "subjects": r["subjects"], "est_hours": eh})
            acc -= eh

    # ---- interleave into one blended list (passion-first per the ratio bias)
    order = []
    pi, fi = 0, 0
    while pi < len(passion) or fi < len(foundations):
        if pi < len(passion):
            order.append(("passion", passion[pi])); pi += 1
        if fi < len(foundations):
            order.append(("foundations", foundations[fi])); fi += 1
    base = int(done["sort_order"].max()) + 1 if not done.empty else 0
    for i, (kind, it) in enumerate(order):
        conn.execute("""INSERT INTO weekly_plan_items
            (student_id, week_start, kind, ref_id, title, subjects, est_hours,
             status, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', ?)""",
            (student_id, monday.isoformat(), kind, it["ref_id"], it["title"],
             it["subjects"], it["est_hours"], base + i))
    conn.commit()


def complete_plan_item(item_id, student_id, school_year):
    """Finish a plan item by routing to the underlying quest/module completion
    (which logs the pending hours), then mark the plan row done."""
    row = conn.execute("""SELECT kind, ref_id, title, subjects, est_hours
        FROM weekly_plan_items WHERE id = ?""", (item_id,)).fetchone()
    if not row:
        return
    kind, ref_id, title, subjects, est_hours = row
    if kind == "passion":
        finish_fun_project(ref_id, student_id, title, subjects, est_hours)
    else:
        complete_foundations_module(ref_id, student_id, title, subjects, est_hours)
    conn.execute("UPDATE weekly_plan_items SET status = 'done' WHERE id = ?", (item_id,))
    conn.commit()


def get_proposals(student_id, status=None):
    q = "SELECT * FROM proposals WHERE student_id = ?"
    params = [student_id]
    if status:
        q += " AND status = ?"
        params.append(status)
    q += " ORDER BY id DESC"
    return pd.read_sql(q, conn, params=params)


def add_proposal(student_id, school_year, prop_type, title, secondary, url, description):
    conn.execute("""INSERT INTO proposals
        (student_id, school_year, prop_type, title, secondary, url, description,
         status, submitted_date, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (student_id, school_year, prop_type, title, secondary, url, description,
         date.today().isoformat(), datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def review_proposal(proposal_id, status, parent_note=""):
    conn.execute("""UPDATE proposals SET status = ?, parent_note = ?,
        reviewed_date = ? WHERE id = ?""",
        (status, parent_note, date.today().isoformat(), proposal_id))
    conn.commit()


def get_elective_deadline(school_year):
    val = setting_get(f"elective_deadline_{school_year}")
    return date.fromisoformat(val) if val else None


def set_elective_deadline(school_year, d):
    setting_set(f"elective_deadline_{school_year}", d.isoformat())


def get_school_year_dates(school_year):
    start = setting_get(f"school_year_start_{school_year}")
    end = setting_get(f"school_year_end_{school_year}")
    return (date.fromisoformat(start) if start else None,
            date.fromisoformat(end) if end else None)


def set_school_year_dates(school_year, start_d, end_d):
    setting_set(f"school_year_start_{school_year}", start_d.isoformat())
    setting_set(f"school_year_end_{school_year}", end_d.isoformat())


def get_holidays_df(school_year=None):
    if school_year:
        return pd.read_sql("SELECT * FROM holidays WHERE school_year = ? "
                           "ORDER BY start_date", conn, params=[school_year])
    return pd.read_sql("SELECT * FROM holidays ORDER BY start_date", conn)


def add_holiday(school_year, start_d, end_d, label):
    conn.execute("""INSERT INTO holidays (school_year, start_date, end_date, label)
        VALUES (?, ?, ?, ?)""",
        (school_year, start_d.isoformat(), end_d.isoformat(), label))
    conn.commit()


def delete_holiday(holiday_id):
    conn.execute("DELETE FROM holidays WHERE id = ?", (holiday_id,))
    conn.commit()


def get_holiday_for_date(school_year, d):
    """Return the holiday label covering date d, or None."""
    df = get_holidays_df(school_year)
    if df.empty:
        return None
    iso = d.isoformat()
    match = df[(df["start_date"] <= iso) & (df["end_date"] >= iso)]
    return match.iloc[0]["label"] if not match.empty else None


def nth_weekday(year, month, weekday, n):
    """weekday: 0=Monday..6=Sunday. n=1 for 1st occurrence in the month, etc."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (n - 1) * 7)


def last_weekday(year, month, weekday):
    """Last occurrence of weekday in the month."""
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() - weekday) % 7)


def federal_holidays_for_year(year):
    """The 11 US federal holidays observed in a given calendar year."""
    return [
        (date(year, 1, 1), "New Year's Day"),
        (nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day"),
        (nth_weekday(year, 2, 0, 3), "Presidents Day"),
        (last_weekday(year, 5, 0), "Memorial Day"),
        (date(year, 6, 19), "Juneteenth"),
        (date(year, 7, 4), "Independence Day"),
        (nth_weekday(year, 9, 0, 1), "Labor Day"),
        (nth_weekday(year, 10, 0, 2), "Columbus Day"),
        (date(year, 11, 11), "Veterans Day"),
        (nth_weekday(year, 11, 3, 4), "Thanksgiving"),
        (date(year, 12, 25), "Christmas Day"),
    ]


def seed_federal_holidays(school_year, start_d, end_d):
    """Add any federal holidays within [start_d, end_d] not already present."""
    existing = get_holidays_df(school_year)
    existing_keys = ({(r["start_date"], r["label"]) for _, r in existing.iterrows()}
                     if not existing.empty else set())
    added = 0
    for year in range(start_d.year, end_d.year + 1):
        for d, label in federal_holidays_for_year(year):
            if start_d <= d <= end_d and (d.isoformat(), label) not in existing_keys:
                add_holiday(school_year, d, d, label)
                added += 1
    return added


def get_checklist_item(school_year, key):
    return setting_get(f"checklist_{key}_{school_year}") == "done"


def set_checklist_item(school_year, key, done):
    setting_set(f"checklist_{key}_{school_year}", "done" if done else "pending")


def get_student_electives(student_id, school_year):
    return pd.read_sql("SELECT * FROM student_electives WHERE student_id = ? "
                       "AND school_year = ? ORDER BY id", conn,
                       params=[student_id, school_year])


def set_student_electives(student_id, school_year, elective_names):
    conn.execute("DELETE FROM student_electives WHERE student_id = ? AND school_year = ?",
                 (student_id, school_year))
    for name in elective_names:
        conn.execute("""INSERT INTO student_electives
            (student_id, school_year, elective_name, selected_date)
            VALUES (?, ?, ?, ?)""",
            (student_id, school_year, name, date.today().isoformat()))
    conn.commit()


def get_student_books(student_id, school_year):
    return pd.read_sql("SELECT * FROM student_books WHERE student_id = ? "
                       "AND school_year = ? ORDER BY id", conn,
                       params=[student_id, school_year])


def add_student_book(student_id, school_year, title, author, ties_to, link):
    conn.execute("""INSERT INTO student_books
        (student_id, school_year, title, author, ties_to, link, status, selected_date)
        VALUES (?, ?, ?, ?, ?, ?, 'planned', ?)""",
        (student_id, school_year, title, author, ties_to, link, date.today().isoformat()))
    conn.commit()


def update_book_status(book_id, status):
    finished = date.today().isoformat() if status == "finished" else None
    finished_at = (datetime.now().isoformat(timespec="seconds")
                  if status == "finished" else None)
    conn.execute("""UPDATE student_books
        SET status = ?, finished_date = ?, finished_at = ? WHERE id = ?""",
        (status, finished, finished_at, book_id))
    conn.commit()


def delete_student_book(book_id):
    conn.execute("DELETE FROM student_books WHERE id = ?", (book_id,))
    conn.commit()


def get_accounts(student_id):
    return pd.read_sql("SELECT * FROM accounts WHERE student_id = ? "
                       "ORDER BY service_name", conn, params=[student_id])


def get_school_email(student_id):
    """Find the saved Google/Gmail account and return its address, if any."""
    accts = get_accounts(student_id)
    if accts.empty:
        return None
    match = accts[accts["service_name"].str.contains("gmail|google", case=False, na=False)]
    if match.empty or not match.iloc[0]["username"]:
        return None
    return match.iloc[0]["username"]


def get_applicable_account_services(student_id, school_year):
    """ACCOUNT_SERVICES filtered to required ones + electives currently picked."""
    chosen = get_student_electives(student_id, school_year)
    chosen_names = set(chosen["elective_name"]) if not chosen.empty else set()
    return {name: info for name, info in ACCOUNT_SERVICES.items()
            if info["required"] or (chosen_names & set(info["electives"]))}


def get_health_habits_day(student_id, log_date):
    row = conn.execute(
        "SELECT exercise, water, sleep, nutrition, journal, mood_rating, "
        "lesson_score, lesson_feedback, friction_tags, rough_subject, "
        "daily_move FROM health_habits WHERE student_id = ? AND log_date = ?",
        (student_id, log_date.isoformat())).fetchone()
    if row is None:
        return {"exercise": 0, "water": 0, "sleep": 0, "nutrition": 0,
                "journal": "", "mood_rating": None, "lesson_score": None,
                "lesson_feedback": "", "friction_tags": [],
                "rough_subject": "", "daily_move": 0}
    return {"exercise": row[0], "water": row[1], "sleep": row[2],
            "nutrition": row[3], "journal": row[4] or "",
            "mood_rating": row[5], "lesson_score": row[6],
            "lesson_feedback": row[7] or "",
            "friction_tags": [t for t in (row[8] or "").split(",") if t],
            "rough_subject": row[9] or "", "daily_move": row[10] or 0}


def set_health_habit(student_id, log_date, habit_key, value):
    valid_keys = {h["key"] for h in HEALTH_HABITS}
    if habit_key not in valid_keys:
        raise ValueError(f"Unknown habit key: {habit_key}")
    conn.execute("""INSERT INTO health_habits (student_id, log_date) VALUES (?, ?)
        ON CONFLICT(student_id, log_date) DO NOTHING""",
        (student_id, log_date.isoformat()))
    conn.execute(f"""UPDATE health_habits SET {habit_key} = ?
        WHERE student_id = ? AND log_date = ?""",
        (int(value), student_id, log_date.isoformat()))
    conn.commit()


def set_health_journal(student_id, log_date, text):
    conn.execute("""INSERT INTO health_habits (student_id, log_date) VALUES (?, ?)
        ON CONFLICT(student_id, log_date) DO NOTHING""",
        (student_id, log_date.isoformat()))
    conn.execute("""UPDATE health_habits SET journal = ?
        WHERE student_id = ? AND log_date = ?""",
        (text, student_id, log_date.isoformat()))
    conn.commit()


def set_health_rating(student_id, log_date, field, value):
    if field not in ("day_rating", "mood_rating"):
        raise ValueError(f"Unknown rating field: {field}")
    conn.execute("""INSERT INTO health_habits (student_id, log_date) VALUES (?, ?)
        ON CONFLICT(student_id, log_date) DO NOTHING""",
        (student_id, log_date.isoformat()))
    conn.execute(f"""UPDATE health_habits SET {field} = ?
        WHERE student_id = ? AND log_date = ?""",
        (value, student_id, log_date.isoformat()))
    conn.commit()


def set_lesson_reflection(student_id, log_date, score, feedback):
    """Today's lesson score (1-5) plus the optional open text field."""
    conn.execute("""INSERT INTO health_habits (student_id, log_date) VALUES (?, ?)
        ON CONFLICT(student_id, log_date) DO NOTHING""",
        (student_id, log_date.isoformat()))
    conn.execute("""UPDATE health_habits SET lesson_score = ?,
        lesson_feedback = ? WHERE student_id = ? AND log_date = ?""",
        (score, feedback, student_id, log_date.isoformat()))
    conn.commit()


def set_friction(student_id, log_date, tags, rough_subject):
    """The tapped friction chips + which subject was roughest."""
    conn.execute("""INSERT INTO health_habits (student_id, log_date) VALUES (?, ?)
        ON CONFLICT(student_id, log_date) DO NOTHING""",
        (student_id, log_date.isoformat()))
    conn.execute("""UPDATE health_habits SET friction_tags = ?, rough_subject = ?
        WHERE student_id = ? AND log_date = ?""",
        (",".join(tags), rough_subject or None, student_id, log_date.isoformat()))
    conn.commit()


def set_daily_move(student_id, log_date, done):
    conn.execute("""INSERT INTO health_habits (student_id, log_date) VALUES (?, ?)
        ON CONFLICT(student_id, log_date) DO NOTHING""",
        (student_id, log_date.isoformat()))
    conn.execute("""UPDATE health_habits SET daily_move = ?
        WHERE student_id = ? AND log_date = ?""",
        (1 if done else 0, student_id, log_date.isoformat()))
    conn.commit()


def get_daily_move(d):
    """Same move all day for a given date, a different one tomorrow."""
    return random.Random(d.toordinal() + 7).choice(DAILY_MOVES)


def debrief_is_done(habits_row):
    """A debrief counts as done once both ratings are in — the two taps that
    carry the actual signal. Deliberately does NOT require the habit boxes:
    gating it on those rewards ticking boxes rather than answering honestly."""
    return (habits_row["mood_rating"] is not None
            and habits_row["lesson_score"] is not None)


def get_health_habits_range(student_id, start_date, end_date):
    return pd.read_sql(
        "SELECT * FROM health_habits WHERE student_id = ? "
        "AND log_date BETWEEN ? AND ? ORDER BY log_date", conn,
        params=[student_id, start_date.isoformat(), end_date.isoformat()])


def get_health_streak(student_id):
    """Consecutive days he actually checked in, ending at the most recently
    completed day (today doesn't break the streak if it's just not filled in
    yet).

    This counts *showing up*, not *doing everything right*. It used to require
    all four habit boxes ticked, which quietly made the streak a reason to
    tick them whether or not they were true — a streak worth protecting is a
    streak worth lying for, and self-reported habits are unverifiable. Rewarding
    the honest report instead means the data is worth reading.
    """
    df = get_health_habits_range(student_id, date.today() - timedelta(days=120),
                                 date.today())
    by_date = {r["log_date"]: r for _, r in df.iterrows()} if not df.empty else {}

    def checked_in(d):
        row = by_date.get(d.isoformat())
        return (row is not None and pd.notna(row["mood_rating"])
                and pd.notna(row["lesson_score"]))

    d = date.today()
    if not checked_in(d):
        d -= timedelta(days=1)
    streak = 0
    while checked_in(d):
        streak += 1
        d -= timedelta(days=1)
    return streak


def upsert_account(student_id, service_name, url, username, password, status,
                    class_code=None):
    existing = conn.execute(
        "SELECT id FROM accounts WHERE student_id = ? AND service_name = ?",
        (student_id, service_name)).fetchone()
    if existing:
        conn.execute("""UPDATE accounts SET url = ?, username = ?, password = ?,
            status = ?, class_code = ? WHERE id = ?""",
            (url, username, password, status, class_code, existing[0]))
    else:
        conn.execute("""INSERT INTO accounts
            (student_id, service_name, url, username, password, status, class_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (student_id, service_name, url, username, password, status, class_code))
    conn.commit()


def delete_account(account_id):
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()


def block_hours(start, end):
    fmt = "%H:%M"
    return round((datetime.strptime(end, fmt) - datetime.strptime(start, fmt)).seconds / 3600, 2)


def format_time12(t):
    """'14:00' -> '2:00 PM' — schedule times are wall-clock Pacific, no military time."""
    return datetime.strptime(t, "%H:%M").strftime("%I:%M %p").lstrip("0")


def grade_summary(student_id):
    df = get_assignments(student_id)
    if df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["score", "max_score"])
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("subject").apply(
        lambda x: 100 * x["score"].sum() / x["max_score"].sum(), include_groups=False
    ).round(1)
    out = pd.DataFrame({"Average %": g})
    out["Letter"] = out["Average %"].apply(letter_grade)
    out["Assignments"] = df.groupby("subject").size()
    return out.reset_index().rename(columns={"subject": "Subject"})


def suggest_quiz_for_day(student_id, d):
    """Pick a quiz topic tied to one of the subjects already scheduled today,
    preferring one that hasn't been taken yet."""
    subjects_today = [b[0] for b in WEEKLY_SCHEDULE.get(d.strftime("%A"), [])]
    ga = get_assignments(student_id)
    for subj in subjects_today:
        topics = QUIZ_BANK.get(subj)
        if not topics:
            continue
        taken = set(ga[ga["subject"] == subj]["title"]) if not ga.empty else set()
        for topic in topics:
            if f"Quiz: {topic}" not in taken:
                return subj, topic
        return subj, next(iter(topics))
    return None, None


def get_daily_trivia(d):
    """Same trivia fact all day for a given date, different fact the next day."""
    rng = random.Random(d.toordinal())
    return rng.choice(TRIVIA_BANK)


def get_quiz_dates(student_id):
    """Set of ISO date strings on which a quiz was taken (from Grading records)."""
    ga = get_assignments(student_id)
    if ga.empty:
        return set()
    return set(ga[ga["title"].str.startswith("Quiz:")]["assign_date"])


def get_finished_fun_project_dates(student_id, school_year):
    """Set of ISO date strings on which a fun project was marked finished."""
    df = get_student_fun_projects(student_id, school_year)
    if df.empty:
        return set()
    finished = df[(df["status"] == "finished") & df["finished_date"].notna()]
    return set(finished["finished_date"])


def count_finished_fun_projects_in_month(student_id, school_year, year, month):
    dates = get_finished_fun_project_dates(student_id, school_year)
    return sum(1 for d in dates
              if date.fromisoformat(d).year == year and date.fromisoformat(d).month == month)


def get_active_fun_project(student_id, school_year):
    """The most recently picked in_progress project, or None."""
    df = get_student_fun_projects(student_id, school_year)
    if df.empty:
        return None
    active = df[df["status"] == "in_progress"]
    return None if active.empty else active.iloc[-1]


def _render_electives_picker(student_id, school_year, key_prefix, is_parent=False):
    """Core electives picking UI. Returns True once at least one is selected."""
    elective_pool = get_elective_pool_dict()
    deadline = get_elective_deadline(school_year)
    locked = (not is_parent) and deadline is not None and date.today() > deadline

    st.caption(f"Pick up to {MAX_ELECTIVES} for the Friday elective block.")
    if deadline:
        if locked:
            st.error(f"⚠️ Selection deadline was {fmt_date(deadline)} — "
                     "ask a parent to update your electives.")
        else:
            days_left = (deadline - date.today()).days
            st.info(f"📌 Pick your electives by {fmt_date(deadline)} "
                    f"({days_left} day{'s' if days_left != 1 else ''} left)")

    chosen = get_student_electives(student_id, school_year)
    chosen_names = list(chosen["elective_name"]) if not chosen.empty else []

    if chosen_names:
        st.markdown("**Current electives:**")
        for name in chosen_names:
            info = elective_pool.get(name)
            if info:
                st.markdown(f"- **{name}** — [{info[0]}]({info[1]})  \n  _{info[2]}_")
            else:
                st.markdown(f"- **{name}** _(no longer offered)_")
        if not locked:
            with st.expander("Change electives"):
                picks = st.multiselect(
                    f"Pick up to {MAX_ELECTIVES}", list(elective_pool.keys()),
                    default=[n for n in chosen_names if n in elective_pool],
                    max_selections=MAX_ELECTIVES, key=f"{key_prefix}_elect_change")
                if st.button("Save electives", key=f"{key_prefix}_save_elect_change"):
                    set_student_electives(student_id, school_year, picks)
                    st.success("Updated!")
                    st.rerun()
    elif locked:
        st.warning("No electives were picked before the deadline — ask a parent to set them.")
    else:
        st.info(f"No electives picked yet — choose up to {MAX_ELECTIVES} below.")
        picks = st.multiselect(f"Pick up to {MAX_ELECTIVES} electives",
                               list(elective_pool.keys()), max_selections=MAX_ELECTIVES,
                               key=f"{key_prefix}_elect_first_pick")
        for name in picks:
            st.caption(f"**{name}**: {elective_pool[name][2]}")
        if st.button("Save electives", type="primary", key=f"{key_prefix}_save_elect_first"):
            if picks:
                set_student_electives(student_id, school_year, picks)
                st.success("Saved!")
                st.rerun()
            else:
                st.warning("Pick at least one.")

    return bool(chosen_names)


def _render_reading_picker(student_id, school_year, key_prefix):
    """Core reading list UI. Returns True once at least one book is on the list."""
    st.caption("Books tied to 8th grade subjects.")
    books = get_student_books(student_id, school_year)
    my_titles = list(books["title"]) if not books.empty else []

    if not books.empty:
        st.markdown("**Current list:**")
        for _, b in books.iterrows():
            with st.container(border=True):
                bc1, bc2, bc3 = st.columns([3, 1.3, 1])
                with bc1:
                    st.markdown(f"**{b['title']}** by {b['author']}")
                    st.caption(b["ties_to"])
                with bc2:
                    opts = ["planned", "reading", "finished"]
                    new_status = st.selectbox(
                        "Status", opts, index=opts.index(b["status"]),
                        key=f"{key_prefix}_book_status_{b['id']}", label_visibility="collapsed")
                    if new_status != b["status"]:
                        update_book_status(int(b["id"]), new_status)
                        st.rerun()
                with bc3:
                    if st.button("Remove", key=f"{key_prefix}_book_del_{b['id']}"):
                        delete_student_book(int(b["id"]))
                        st.rerun()

    st.markdown("**Add from the 8th grade book pool:**")
    for _, book in get_book_pool_df().iterrows():
        if book["title"] in my_titles:
            continue
        with st.container(border=True):
            bc1, bc2 = st.columns([4, 1])
            with bc1:
                st.markdown(f"🔗 [**{book['title']}**]({book['link']}) by {book['author']}")
                st.caption(book["ties_to"])
            with bc2:
                if st.button("Add", key=f"{key_prefix}_book_add_{book['title']}"):
                    add_student_book(student_id, school_year, book["title"],
                                     book["author"], book["ties_to"], book["link"])
                    st.rerun()

    return not books.empty


def render_electives_books(student_id, school_year, key_prefix, is_parent=False):
    """Flat electives + reading list panel — used in the Parent Curriculum tab."""
    st.subheader(f"Electives — {school_year}")
    _render_electives_picker(student_id, school_year, key_prefix, is_parent)

    st.divider()
    st.subheader(f"Reading list — {school_year}")
    _render_reading_picker(student_id, school_year, key_prefix)


def render_student_curriculum_setup(student_id, school_year):
    """Student-only: collapsible Day 1/2 setup — propose, pick electives, pick books."""
    school_start, _ = get_school_year_dates(school_year)
    day2_unlock = (school_start + timedelta(days=1)) if school_start else None
    day2_locked = day2_unlock is not None and date.today() < day2_unlock

    propose_done = get_checklist_item(school_year, "propose_done")
    with st.expander(f"{'✅ ' if propose_done else ''}💡 Day 1: Propose "
                     "something new", expanded=not propose_done):
        render_proposals_student(student_id, school_year)

    elect_done = not get_student_electives(student_id, school_year).empty
    if day2_locked:
        with st.container(border=True):
            st.markdown("🔒 **Day 2: Select your electives**")
            st.caption(f"Unlocks {fmt_date(day2_unlock)} — "
                       "propose anything you want on Day 1 first, and your "
                       "parent will review it overnight so it's ready to pick "
                       "from.")
    else:
        with st.expander(f"{'✅ ' if elect_done else ''}🎯 Day 2: Select your "
                         "electives", expanded=not elect_done):
            _render_electives_picker(student_id, school_year, key_prefix="stu")

    books_done = not get_student_books(student_id, school_year).empty
    if day2_locked:
        with st.container(border=True):
            st.markdown("🔒 **Day 2: Build your reading list**")
            st.caption(f"Unlocks {fmt_date(day2_unlock)}, same as "
                       "electives.")
    else:
        with st.expander(f"{'✅ ' if books_done else ''}📚 Day 2: Build your "
                         "reading list", expanded=not books_done):
            _render_reading_picker(student_id, school_year, key_prefix="stu")


def render_pool_admin(subheader, caption, df, id_col, fields, add_fn, update_fn,
                       delete_fn, key_prefix, expander_label_fn=None):
    """Generic add/edit/delete admin panel shared by the electives, books, and
    fun-project pools. fields: list of (column, label, kind) where kind is
    'text', 'textarea', or a list of options (rendered as a selectbox).
    add_fn/update_fn are called with field values in `fields` order (update_fn
    gets the row id first). IntegrityError (e.g. a UNIQUE column) shows as a
    friendly warning instead of crashing."""
    st.subheader(subheader)
    st.caption(caption)

    def _widget(col, label, kind, default, key):
        if kind == "textarea":
            return st.text_area(label, value=default, key=key)
        if isinstance(kind, list):
            return st.selectbox(label, kind, index=kind.index(default)
                                if default in kind else 0, key=key)
        return st.text_input(label, value=default, key=key)

    for _, row in df.iterrows():
        label = expander_label_fn(row) if expander_label_fn else str(row[fields[0][0]])
        with st.expander(label):
            with st.form(key=f"{key_prefix}_edit_{row[id_col]}"):
                values = [_widget(col, lbl, kind, row[col] or "",
                                  f"{key_prefix}_{col}_{row[id_col]}")
                         for col, lbl, kind in fields]
                c1, c2 = st.columns(2)
                with c1:
                    save = st.form_submit_button("Save changes")
                with c2:
                    remove = st.form_submit_button("Delete")
            if save:
                if str(values[0]).strip():
                    cleaned = [v.strip() if isinstance(v, str) else v for v in values]
                    try:
                        update_fn(int(row[id_col]), *cleaned)
                        st.success("Updated.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"A {fields[0][1].lower()} like that already exists.")
                else:
                    st.warning(f"{fields[0][1]} can't be blank.")
            if remove:
                delete_fn(int(row[id_col]))
                st.rerun()

    st.markdown("**Add new**")
    with st.form(f"{key_prefix}_add", clear_on_submit=True):
        values = [_widget(col, lbl, kind, kind[0] if isinstance(kind, list) else "",
                          f"{key_prefix}_add_{col}")
                 for col, lbl, kind in fields]
        if st.form_submit_button("Add"):
            if str(values[0]).strip():
                cleaned = [v.strip() if isinstance(v, str) else v for v in values]
                try:
                    add_fn(*cleaned)
                    st.success("Added.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"A {fields[0][1].lower()} like that already exists.")
            else:
                st.warning(f"Give it a {fields[0][1].lower()}.")


def render_elective_pool_admin(school_year):
    """Parent-only: set the selection deadline and manage the elective options pool."""
    st.subheader("Manage electives")

    st.markdown("**Selection deadline**")
    st.caption("Once this date passes, he can no longer pick or change his own "
               "electives on his own — you still can, any time. Typically the "
               "school start date.")
    current_deadline = get_elective_deadline(school_year)
    new_deadline = st.date_input("School start date / selection deadline",
                                 value=current_deadline or date.today(),
                                 format="MM-DD-YYYY", key="elect_deadline_input")
    if st.button("Save deadline", key="save_elect_deadline"):
        set_elective_deadline(school_year, new_deadline)
        st.success(f"Deadline set to {fmt_date(new_deadline)}.")
        st.rerun()

    st.divider()
    render_pool_admin(
        "Elective options pool",
        "Add, edit, or remove what shows up for him to choose from.",
        get_elective_pool_df(), "id",
        [("name", "Name", "text"), ("resource_name", "Resource name", "text"),
         ("url", "URL", "text"), ("description", "Description", "textarea")],
        add_elective_pool_option, update_elective_pool_option,
        delete_elective_pool_option, key_prefix="pool")


def render_book_pool_admin():
    """Parent-only: manage the book pool options."""
    render_pool_admin(
        "Book pool",
        "Add, edit, or remove what shows up in his reading list picker.",
        get_book_pool_df(), "id",
        [("title", "Title", "text"), ("author", "Author", "text"),
         ("ties_to", "Ties to", "textarea"), ("link", "Link", "text")],
        add_book_pool_option, update_book_pool_option, delete_book_pool_option,
        key_prefix="bookpool")


def render_scope_reference():
    """Read-only 8th grade scope reference — shown in both Student and Parent views."""
    st.subheader("Typical 8th Grade Scope")
    st.info(SCOPE_FRAMING_NOTE)
    for subject, desc in SCOPE_BY_SUBJECT.items():
        with st.expander(subject):
            st.markdown(desc)


def render_passion_intake(student_id, key_prefix):
    """The interest/values intake — a tappable 'passion profile' that the
    weekly blender uses to rank which quests to surface. Kept to chips + one
    short goal so a 13-year-old actually completes it."""
    prof = get_passion_profile(student_id)
    has_profile = bool(prof["interests"])
    with st.expander("✨ What are you into? (helps pick your quests)",
                     expanded=not has_profile):
        st.caption("Tap everything that sounds like you. Change it whenever.")
        interests = st.pills("Interests", INTEREST_OPTIONS, selection_mode="multi",
                            default=prof["interests"],
                            key=f"{key_prefix}_interests",
                            label_visibility="collapsed")
        interests = interests or []
        goal = st.text_input(
            "One thing you'd love to get good at this year",
            value=prof["core_values"], key=f"{key_prefix}_goal",
            placeholder="e.g. draw my own comic, edit videos, cook dinner")
        if interests != prof["interests"] or goal != prof["core_values"]:
            set_passion_profile(student_id, interests, goal.strip())
            st.rerun()
        if has_profile:
            st.success("Locked in — your quests lean toward this now.")


def render_fun_projects_picker(student_id, school_year, key_prefix):
    """Browse and pick major quests for the year; track status. Used by both views."""
    st.subheader("🗺️ Passion Track — Quests Built Around You")
    st.caption("Bigger real-world projects that follow what you're into — pick "
               "what sounds fun, not all of them need doing. Finishing one sends "
               "the hours to a parent for approval automatically.")
    st.markdown(QUEST_CARD_CSS, unsafe_allow_html=True)
    render_passion_intake(student_id, key_prefix)

    mine = get_student_fun_projects(student_id, school_year)
    my_titles = list(mine["title"]) if not mine.empty else []
    active = mine[mine["status"] == "in_progress"] if not mine.empty else mine
    queued = mine[mine["status"] == "planned"] if not mine.empty else mine
    finished = mine[mine["status"] == "finished"] if not mine.empty else mine
    total_hours = finished["est_hours"].fillna(1.0).sum() if not finished.empty else 0.0

    m1, m2, m3 = st.columns(3)
    m1.metric("🏆 Quests Completed", len(finished))
    m2.metric("⚔️ Hours Earned", f"{total_hours:.1f}")
    m3.metric("📜 In Progress", len(active))
    st.divider()

    if not active.empty:
        st.markdown("### ⚔️ Active Quest" + ("s" if len(active) > 1 else ""))
        for _, p in active.iterrows():
            ac1, ac2 = st.columns([2, 3])
            with ac1:
                render_quest_card(p, "active")
            with ac2:
                steps = parse_steps(p["steps"])
                if steps:
                    with st.expander("📋 Steps"):
                        for i, s in enumerate(steps, 1):
                            st.markdown(f"{i}. {s}")
                bc1, bc2, bc3 = st.columns(3)
                if bc1.button("🏆 Complete", key=f"{key_prefix}_proj_finish_{p['id']}",
                             type="primary", use_container_width=True):
                    finish_fun_project(int(p["id"]), student_id, p["title"],
                                      p["subjects"] or p["subject"], p["est_hours"] or 1.0)
                    st.success("Quest complete! Sent to your parent for approval.")
                    st.rerun()
                if bc2.button("⏸️ Pause", key=f"{key_prefix}_proj_pause_{p['id']}",
                             use_container_width=True):
                    update_fun_project_status(int(p["id"]), "planned")
                    st.rerun()
                if bc3.button("🗑️ Remove", key=f"{key_prefix}_proj_del_{p['id']}",
                             use_container_width=True):
                    delete_student_fun_project(int(p["id"]))
                    st.rerun()
        st.divider()

    if not queued.empty:
        st.markdown("### 📜 Queued Quests")
        qcols = st.columns(3)
        for i, (_, p) in enumerate(queued.iterrows()):
            with qcols[i % 3]:
                render_quest_card(p, "queued")
                if st.button("▶️ Start Quest", key=f"{key_prefix}_proj_start_{p['id']}",
                            type="primary", use_container_width=True):
                    update_fun_project_status(int(p["id"]), "in_progress")
                    st.rerun()
                if st.button("🗑️ Remove", key=f"{key_prefix}_proj_qdel_{p['id']}",
                            use_container_width=True):
                    delete_student_fun_project(int(p["id"]))
                    st.rerun()
        st.divider()

    st.markdown("### 🗺️ Available Quests")
    pool = get_fun_project_pool_df()
    tag_map = {}
    for _, proj in pool.iterrows():
        tags = [t.strip() for t in (proj["subjects"] or proj["subject"] or "").split(",")
               if t.strip()]
        for tag in tags:
            tag_map.setdefault(tag, []).append(proj)
    for subj in sorted(tag_map):
        available = [p for p in tag_map[subj] if p["title"] not in my_titles]
        if not available:
            continue
        with st.expander(f"{subj} ({len(available)})"):
            cols = st.columns(3)
            for i, proj in enumerate(available):
                with cols[i % 3]:
                    render_quest_card(proj, "queued")
                    if st.button("➕ Add to My Quests",
                                key=f"{key_prefix}_proj_add_{proj['id']}_{subj}",
                                use_container_width=True):
                        add_student_fun_project(
                            student_id, school_year, proj["title"],
                            proj["subjects"] or proj["subject"], proj["description"],
                            proj["steps"], proj["est_hours"] or 1.0, proj["icon"])
                        st.rerun()

    if not finished.empty:
        st.divider()
        with st.expander(f"🏆 Trophy Case ({len(finished)} completed)"):
            fcols = st.columns(3)
            for i, (_, p) in enumerate(finished.sort_values("finished_date", ascending=False).iterrows()):
                with fcols[i % 3]:
                    render_quest_card(p, "done")
                    st.caption(f"Finished {fmt_date(p['finished_date'])}")


def render_fun_project_pool_admin():
    """Parent-only: manage the major-quest backlog."""
    render_pool_admin(
        "Quest backlog",
        "Add, edit, or remove major quests for the year — this is the pool "
        "he picks from, not a required checklist.",
        get_fun_project_pool_df(), "id",
        [("title", "Title", "text"),
         ("subjects", "Subjects (comma-separated, exact match — e.g. "
                      "\"Writing, Occupational Education\")", "text"),
         ("description", "Description", "textarea"),
         ("steps", "Steps (one per line — leave blank for open-ended)", "textarea"),
         ("mess_level", "Mess level", ["Low", "Medium", "High"]),
         ("est_hours", "Estimated hours (e.g. 1.0, 2.5)", "text"),
         ("icon", "Icon (a single emoji, e.g. 🎬 or 🧱)", "text")],
        add_fun_project_pool_option, update_fun_project_pool_option,
        delete_fun_project_pool_option, key_prefix="funpool",
        expander_label_fn=lambda row: f"{row['title']} "
                                      f"({row['subjects'] or row['subject']}) · "
                                      f"{row['mess_level'] or 'Low'} mess")


# Emoji per Foundations pillar — keeps the library scannable and on-brand.
FOUNDATIONS_PILLAR_ICON = {
    "Financial Literacy": "💰", "Digital Literacy": "🌐",
    "Career Readiness": "🧭", "Health & Wellness": "🫀",
    "Life Skills": "🛠️", "Civics": "🏛️",
}


def render_foundations(student_id, school_year, key_prefix):
    """Student-facing Foundations Track: the mandatory life-skills half of
    Compass. Browse modules by pillar, open one, do the activities, mark it
    complete → logs pending hours like a quest. Styled as cards, not a list."""
    st.subheader("🧭 Foundations")
    st.caption("The real-world stuff school skips — money, cooking, digital "
               "smarts, your rights. Finish one and the hours go to a parent, "
               "same as a quest.")
    st.markdown(QUEST_CARD_CSS, unsafe_allow_html=True)

    df = get_student_foundations(student_id)
    if df.empty:
        st.info("No Foundations modules yet — a parent can add them in "
                "Parent Console → 🧭 Foundations.")
        return

    done_mask = df["prog_status"] == "complete"
    done_ct = int(done_mask.sum())
    total = len(df)
    st.progress(done_ct / total,
                text=f"🏅 {done_ct} / {total} Foundations badges earned")

    for pillar in [p for p in FOUNDATIONS_PILLARS if p in set(df["pillar"])]:
        chunk = df[df["pillar"] == pillar]
        icon = FOUNDATIONS_PILLAR_ICON.get(pillar, "•")
        pdone = int((chunk["prog_status"] == "complete").sum())
        st.markdown(f"### {icon} {pillar}  ·  {pdone}/{len(chunk)}")
        for _, m in chunk.iterrows():
            is_done = m["prog_status"] == "complete"
            with st.container(border=True):
                head = f"{'✅' if is_done else '⬜'} **{m['title']}**"
                st.markdown(head)
                st.caption(m["description"] or "")
                with st.expander("What you'll get out of it + how to do it"):
                    if m["objectives"]:
                        st.markdown(f"**You'll be able to:** {m['objectives']}")
                    steps = [s for s in (m["activities"] or "").split("\n") if s.strip()]
                    if steps:
                        st.markdown("**Do this:**")
                        for i, s in enumerate(steps, 1):
                            st.markdown(f"{i}. {s}")
                    if m["source_url"]:
                        st.markdown(f"🔗 [Start here]({m['source_url']})")
                    tags = ", ".join(t.strip() for t in (m["subjects"] or "").split(",")
                                     if t.strip())
                    st.caption(f"Counts toward: {tags} · ~{m['est_hours'] or 1.0:g} hr")
                if is_done:
                    when = str(m["completed_at"])[:10] if m["completed_at"] else ""
                    c1, c2 = st.columns([3, 1])
                    c1.success(f"Done{f' · {when}' if when else ''}")
                    if c2.button("Reopen", key=f"{key_prefix}_reopen_{m['id']}",
                                 use_container_width=True):
                        reopen_foundations_module(int(m["id"]), student_id)
                        st.rerun()
                else:
                    if st.button("🏅 Mark complete",
                                 key=f"{key_prefix}_done_{m['id']}", type="primary"):
                        complete_foundations_module(
                            int(m["id"]), student_id, m["title"],
                            m["subjects"], m["est_hours"] or 1.0)
                        st.success("Nice — sent to your parent for approval.")
                        st.balloons()
                        st.rerun()


def render_foundations_admin():
    """Parent-only: manage the Foundations library. Bespoke rather than
    render_pool_admin because a module needs a pillar selectbox and a
    multiselect of WA subjects, neither of which that generic helper supports."""
    st.subheader("🧭 Foundations Library")
    st.caption("The life-skills/finance modules he works through. Edit freely — "
               "these seed once, so your changes and deletions stick.")

    df = get_foundations_modules_df(active_only=False)

    def _module_form(row=None):
        pfx = f"fnd_edit_{row['id']}" if row is not None else "fnd_add"
        title = st.text_input("Title", value=row["title"] if row is not None else "",
                              key=f"{pfx}_title")
        pillar = st.selectbox("Pillar", FOUNDATIONS_PILLARS,
                              index=FOUNDATIONS_PILLARS.index(row["pillar"])
                              if row is not None and row["pillar"] in FOUNDATIONS_PILLARS
                              else 0, key=f"{pfx}_pillar")
        cur_subj = [s.strip() for s in (row["subjects"] or "").split(",")
                    if s.strip()] if row is not None else []
        subjects = st.multiselect("Counts toward (WA subjects)",
                                  WA_SUBJECTS + ["Electives"], default=cur_subj,
                                  key=f"{pfx}_subjects")
        description = st.text_input("One-line description",
                                    value=row["description"] if row is not None else "",
                                    key=f"{pfx}_desc")
        objectives = st.text_area("Objectives (what he'll be able to do)",
                                  value=row["objectives"] if row is not None else "",
                                  key=f"{pfx}_obj")
        activities = st.text_area("Activities (one per line)",
                                  value=row["activities"] if row is not None else "",
                                  key=f"{pfx}_act")
        source_url = st.text_input("Source link",
                                   value=row["source_url"] if row is not None else "",
                                   key=f"{pfx}_url")
        est_hours = st.number_input("Estimated hours", min_value=0.25, step=0.25,
                                    value=float(row["est_hours"] or 1.0)
                                    if row is not None else 1.0, key=f"{pfx}_hrs")
        return (title, pillar, description, objectives, activities,
                ", ".join(subjects), est_hours, source_url)

    by_pillar = {}
    for _, r in df.iterrows():
        by_pillar.setdefault(r["pillar"], []).append(r)
    for pillar in FOUNDATIONS_PILLARS:
        rows = by_pillar.get(pillar, [])
        if not rows:
            continue
        st.markdown(f"**{FOUNDATIONS_PILLAR_ICON.get(pillar, '•')} {pillar}**")
        for row in rows:
            with st.expander(row["title"]):
                with st.form(f"fnd_edit_form_{row['id']}"):
                    vals = _module_form(row)
                    c1, c2 = st.columns(2)
                    save = c1.form_submit_button("Save changes")
                    remove = c2.form_submit_button("Delete")
                if save:
                    if vals[0].strip():
                        update_foundations_module(int(row["id"]), *vals)
                        st.success("Updated.")
                        st.rerun()
                    else:
                        st.warning("Title can't be blank.")
                if remove:
                    delete_foundations_module(int(row["id"]))
                    st.rerun()

    st.markdown("**Add a module**")
    with st.form("fnd_add_form", clear_on_submit=True):
        vals = _module_form(None)
        if st.form_submit_button("Add"):
            if vals[0].strip():
                add_foundations_module(*vals)
                st.success("Added.")
                st.rerun()
            else:
                st.warning("Give it a title.")


def _plan_item_done(item, fin_quest_ids, done_module_ids):
    """A plan item counts as done if its own row says so OR the underlying
    quest/module was finished elsewhere (Passion Track / Foundations tab)."""
    if item["status"] == "done":
        return True
    if item["kind"] == "passion":
        return int(item["ref_id"]) in fin_quest_ids
    return int(item["ref_id"]) in done_module_ids


def render_this_week(student_id, school_year, key_prefix):
    """The blended weekly plan — the defining Compass mechanic. Passion quests
    and Foundations modules in ONE sprint board at the parent-set ratio, so
    life skills are woven in, not bolted on."""
    st.subheader("🧭 My Plan — this week")
    st.markdown(QUEST_CARD_CSS, unsafe_allow_html=True)
    monday = _monday_of(date.today())
    plan = get_weekly_plan(student_id, monday)
    s = get_blend_settings(student_id)

    if plan.empty:
        st.info("No plan for this week yet.")
        st.caption(f"Your mix: {s['ratio']}% passion / {100 - s['ratio']}% "
                   f"foundations, about {s['target']:g} hours of projects.")
        if st.button("✨ Build my week", type="primary",
                     key=f"{key_prefix}_build"):
            generate_weekly_plan(student_id, school_year, monday)
            st.rerun()
        return

    fin_quest_ids = {int(r["id"]) for _, r in
                     get_student_fun_projects(student_id, school_year).iterrows()
                     if r["status"] == "finished"}
    sf = get_student_foundations(student_id)
    done_module_ids = {int(r["id"]) for _, r in sf.iterrows()
                       if r["prog_status"] == "complete"} if not sf.empty else set()

    items = [dict(r) for _, r in plan.iterrows()]
    for it in items:
        it["_done"] = _plan_item_done(it, fin_quest_ids, done_module_ids)
    done_ct = sum(1 for it in items if it["_done"])
    st.progress(done_ct / len(items),
                text=f"🔥 {done_ct} / {len(items)} done this week")
    st.caption(f"Mix: {s['ratio']}% passion / {100 - s['ratio']}% foundations. "
               "Parents set the mix in the Plan Blender.")

    kind_badge = {"passion": "🗺️ Passion", "foundations": "🧭 Foundations"}
    kind_color = {"passion": "#4FC3E8", "foundations": "#6FCF7A"}
    todo = [it for it in items if not it["_done"]]
    done = [it for it in items if it["_done"]]

    lane_todo, lane_done = st.columns(2)
    with lane_todo:
        st.markdown(f'<div class="slane-head">🎯 To do ({len(todo)})</div>',
                    unsafe_allow_html=True)
        if not todo:
            st.markdown("**Week's done. Legend. 🏆**")
        for it in todo:
            st.markdown(f"""
                <div class="bcard"><div class="bcard-strip"
                  style="background:{kind_color[it['kind']]}"></div>
                <div class="bcard-in"><div class="bcard-t">{escape_html(it['title'])}</div>
                <div class="bcard-when">{kind_badge[it['kind']]} · {it['est_hours']:g} hr</div>
                </div></div>""",
                unsafe_allow_html=True)
            if st.button("✅ Done", key=f"{key_prefix}_done_{it['id']}",
                         use_container_width=True):
                complete_plan_item(int(it["id"]), student_id, school_year)
                st.success("Logged — sent to your parent.")
                st.rerun()
    with lane_done:
        st.markdown(f'<div class="slane-head done">✅ Done ({len(done)})</div>',
                    unsafe_allow_html=True)
        if not done:
            st.caption("Move a card over. 👉")
        for it in done:
            st.markdown(f"""
                <div class="bcard is-done"><div class="bcard-strip"
                  style="background:{kind_color[it['kind']]}"></div>
                <div class="bcard-in"><div class="bcard-t">{escape_html(it['title'])}</div>
                <div class="bcard-when">{kind_badge[it['kind']]}</div></div></div>""",
                unsafe_allow_html=True)

    st.divider()
    if st.button("🔄 Rebuild this week", key=f"{key_prefix}_regen"):
        generate_weekly_plan(student_id, school_year, monday)
        st.rerun()
    st.caption("Rebuilding keeps what you've finished and refreshes the rest.")


def render_plan_blender(student_id, school_year):
    """Parent-only: set the passion/foundations ratio + weekly hours, and
    (re)generate his blended week."""
    st.subheader("🎛️ Plan Blender")
    st.caption("How his week is mixed. The blender fills the passion share from "
               "his quests (matched to his interests) and the rest from "
               "Foundations modules he hasn't done yet.")
    s = get_blend_settings(student_id)
    ratio = st.slider("Passion share of the week", 0, 100, s["ratio"], step=10,
                      help="The rest is Foundations. 60 means 60% passion / "
                           "40% foundations.")
    st.caption(f"→ {ratio}% passion · {100 - ratio}% foundations")
    target = st.number_input("Weekly project hours to plan for", min_value=1.0,
                             max_value=30.0, step=1.0, value=float(s["target"]))
    if st.button("Save mix", type="primary"):
        set_blend_settings(student_id, ratio, target)
        st.success("Saved.")
        st.rerun()

    st.divider()
    monday = _monday_of(date.today())
    plan = get_weekly_plan(student_id, monday)
    if plan.empty:
        st.info("No plan generated for this week yet.")
    else:
        p_h = plan[plan["kind"] == "passion"]["est_hours"].sum()
        f_h = plan[plan["kind"] == "foundations"]["est_hours"].sum()
        st.markdown(f"**This week:** {len(plan)} items · "
                    f"{p_h:g} passion hrs / {f_h:g} foundations hrs")
        show = plan[["title", "kind", "est_hours", "status"]].rename(columns={
            "title": "Item", "kind": "Track", "est_hours": "Hrs", "status": "Status"})
        st.dataframe(show, use_container_width=True, hide_index=True)
    if st.button("🔄 Generate / rebuild this week"):
        generate_weekly_plan(student_id, school_year, monday)
        st.rerun()


def build_esa_packet_html(student_id, student_row, school_year):
    """A self-contained, print-ready records packet. The Foundations section
    lists each completed module's objectives — that's the 'documented
    educational purpose' an ESA reimbursement wants, which a bare hours CSV
    doesn't carry. Returns a full HTML document string (parent prints to PDF)."""
    name = student_row["name"]
    grade = student_row["grade"] or ""
    approved = get_entries(student_id, statuses=["approved"])
    total_hours = float(approved["hours"].sum()) if not approved.empty else 0.0
    days = approved["entry_date"].nunique() if not approved.empty else 0
    start, end = get_school_year_dates(school_year)
    if start and end:
        span = f"{fmt_date(start)} – {fmt_date(end)}"
    elif not approved.empty:
        span = f"{fmt_date(approved['entry_date'].min())} – {fmt_date(approved['entry_date'].max())}"
    else:
        span = "—"

    def esc(x):
        return escape_html(str(x))

    # hours by subject
    subj_rows = ""
    if not approved.empty:
        by = approved.groupby("subject")["hours"].sum().sort_values(ascending=False)
        for subj, h in by.items():
            subj_rows += f"<tr><td>{esc(subj)}</td><td class='n'>{h:.1f}</td></tr>"
    else:
        subj_rows = "<tr><td colspan='2'>No approved hours yet.</td></tr>"

    # completed Foundations, with objectives = documented educational purpose
    sf = get_student_foundations(student_id)
    fnd_rows = ""
    if not sf.empty:
        fdone = sf[sf["prog_status"] == "complete"]
        for _, m in fdone.iterrows():
            when = str(m["completed_at"])[:10] if m["completed_at"] else ""
            fnd_rows += (f"<tr><td>{esc(m['title'])}<div class='muted'>"
                         f"{esc(m['pillar'])}</div></td>"
                         f"<td>{esc(m['objectives'] or '')}</td>"
                         f"<td class='n'>{esc(m['subjects'] or '')}</td>"
                         f"<td class='n'>{when}</td></tr>")
    if not fnd_rows:
        fnd_rows = "<tr><td colspan='4'>None completed yet.</td></tr>"

    # completed Passion projects
    mine = get_student_fun_projects(student_id, school_year)
    quest_rows = ""
    if not mine.empty:
        for _, p in mine[mine["status"] == "finished"].iterrows():
            when = fmt_date(p["finished_date"]) if p["finished_date"] else ""
            quest_rows += (f"<tr><td>{esc(p['title'])}</td>"
                           f"<td class='n'>{esc(p['subjects'] or p['subject'] or '')}</td>"
                           f"<td class='n'>{when}</td></tr>")
    if not quest_rows:
        quest_rows = "<tr><td colspan='3'>None finished yet.</td></tr>"

    # grades
    ga = get_assignments(student_id)
    grade_rows = ""
    if not ga.empty:
        for _, g in ga.iterrows():
            pct = (f" ({100 * g['score'] / g['max_score']:.0f}%)"
                   if g["max_score"] else "")
            grade_rows += (f"<tr><td>{esc(fmt_date(g['assign_date']))}</td>"
                           f"<td>{esc(g['subject'])}</td><td>{esc(g['title'])}</td>"
                           f"<td class='n'>{esc(g['score'])}/{esc(g['max_score'])}{pct}</td></tr>")
    if not grade_rows:
        grade_rows = "<tr><td colspan='4'>No grades recorded.</td></tr>"

    # assessments
    hist = get_assessments(student_id)
    assess_rows = ""
    if not hist.empty:
        for _, a in hist.iterrows():
            assess_rows += (f"<tr><td>{esc(fmt_date(a['assessment_date']))}</td>"
                            f"<td>{esc(a['assessment_type'])}</td>"
                            f"<td>{esc(a['evaluator'] or '')}</td>"
                            f"<td>{esc(a['result'] or '')}</td></tr>")
    if not assess_rows:
        assess_rows = "<tr><td colspan='4'>No assessment on record.</td></tr>"

    generated = date.today().strftime("%B %d, %Y")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{esc(name)} — Homeschool Records {esc(school_year)}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; color:#1a1a1a;
    max-width: 820px; margin: 24px auto; padding: 0 20px; }}
  h1 {{ margin: 0 0 2px; font-size: 24px; }}
  h2 {{ margin: 26px 0 8px; font-size: 15px; text-transform: uppercase;
    letter-spacing: .05em; border-bottom: 2px solid #1a1a1a; padding-bottom: 4px; }}
  .sub {{ color:#555; margin-bottom: 14px; }}
  .cards {{ display:flex; gap: 12px; margin: 10px 0 4px; }}
  .stat {{ border:1px solid #ccc; border-radius:8px; padding:10px 14px; flex:1; }}
  .stat b {{ font-size: 22px; display:block; }}
  table {{ width:100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align:left; padding:6px 8px; border-bottom:1px solid #e2e2e2;
    vertical-align: top; }}
  th {{ background:#f4f4f4; }}
  td.n, th.n {{ white-space: nowrap; }}
  .muted {{ color:#777; font-size: 11px; }}
  .foot {{ margin-top: 28px; color:#777; font-size: 11px; }}
  @media print {{ body {{ margin: 0; }} h2 {{ page-break-after: avoid; }} }}
</style></head><body>
<h1>Homeschool Records — {esc(name)}</h1>
<div class="sub">{esc(grade)} · School year {esc(school_year)} · {esc(span)}<br>
  Generated {generated} · Washington State (RCW 28A.200)</div>
<div class="cards">
  <div class="stat"><b>{total_hours:.0f}</b>approved instruction hours
    <div class="muted">of 1,000</div></div>
  <div class="stat"><b>{days}</b>days of instruction<div class="muted">of 180</div></div>
  <div class="stat"><b>{int((sf['prog_status'] == 'complete').sum()) if not sf.empty else 0}</b>
    life-skills modules<div class="muted">Foundations completed</div></div>
</div>
<h2>Hours by subject</h2>
<table><thead><tr><th>Subject</th><th class="n">Hours</th></tr></thead>
<tbody>{subj_rows}</tbody></table>
<h2>Foundations completed — educational purpose</h2>
<table><thead><tr><th>Module</th><th>What was learned</th><th class="n">Subjects</th>
<th class="n">Date</th></tr></thead><tbody>{fnd_rows}</tbody></table>
<h2>Passion projects completed</h2>
<table><thead><tr><th>Project</th><th class="n">Subjects</th><th class="n">Date</th></tr></thead>
<tbody>{quest_rows}</tbody></table>
<h2>Grades</h2>
<table><thead><tr><th>Date</th><th>Subject</th><th>Assignment</th><th class="n">Score</th></tr></thead>
<tbody>{grade_rows}</tbody></table>
<h2>Annual assessment</h2>
<table><thead><tr><th>Date</th><th>Type</th><th>Evaluator</th><th>Result</th></tr></thead>
<tbody>{assess_rows}</tbody></table>
<div class="foot">Prepared with Compass. This packet documents instruction hours
  and educational purpose for homeschool records and, where applicable, ESA
  reimbursement. Verify your program's specific requirements.</div>
</body></html>"""


def render_resources_tab(parent_mode):
    """Browsable curriculum material library — photos, documents, or links.
    Parent can add/remove material; both views browse the same list."""
    st.subheader("📎 Resources")
    st.caption("Photos, documents, or links added to go with the curriculum.")

    if parent_mode:
        with st.expander("➕ Add material"):
            title = st.text_input("Title", key="mat_title")
            subject = st.selectbox("Subject", WA_SUBJECTS + ["Electives"], key="mat_subject")
            kind_label = st.radio("Type", ["📷 Photo", "📄 Document", "🔗 Link"],
                                  key="mat_kind", horizontal=True)
            uploaded, url = None, None
            if kind_label == "🔗 Link":
                url = st.text_input("URL (video, article, website...)", key="mat_url")
            elif kind_label == "📷 Photo":
                uploaded = st.file_uploader("Upload photo", type=["jpg", "jpeg", "png"],
                                            key="mat_file_photo")
            else:
                uploaded = st.file_uploader("Upload document",
                                            type=["pdf", "doc", "docx"], key="mat_file_doc")
            notes = st.text_area("Notes (optional)", key="mat_notes")
            if st.button("Add material", key="mat_add_btn"):
                if not title.strip():
                    st.warning("Give it a title.")
                elif kind_label == "🔗 Link" and not (url or "").strip():
                    st.warning("Add a URL.")
                elif kind_label != "🔗 Link" and uploaded is None:
                    st.warning("Choose a file to upload.")
                else:
                    kind = {"📷 Photo": "photo", "📄 Document": "document",
                            "🔗 Link": "link"}[kind_label]
                    file_path = save_uploaded_curriculum_file(uploaded) if uploaded else None
                    add_curriculum_material(title.strip(), subject, kind, file_path,
                                            (url or "").strip() or None, notes.strip())
                    st.success("Added.")
                    st.rerun()
        st.divider()

    materials = get_curriculum_materials()
    if materials.empty:
        st.info("No materials added yet." if parent_mode else "No materials yet.")
        return

    subjects = sorted(materials["subject"].dropna().unique())
    if materials["subject"].isna().any():
        subjects.append(None)

    for subject in subjects:
        subset = materials[materials["subject"] == subject] if subject is not None \
            else materials[materials["subject"].isna()]
        with st.expander(subject or "Uncategorized"):
            for _, m in subset.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        badge = " 🆕" if not m["seen"] else ""
                        st.markdown(f"**{m['title']}**{badge}")
                        if m["notes"]:
                            st.caption(m["notes"])
                        if m["kind"] == "photo" and m["file_path"]:
                            full_path = Path(__file__).parent / m["file_path"]
                            if full_path.exists():
                                st.image(str(full_path), width=300)
                        elif m["kind"] == "document" and m["file_path"]:
                            full_path = Path(__file__).parent / m["file_path"]
                            if full_path.exists():
                                st.download_button(
                                    "⬇️ Open document", full_path.read_bytes(),
                                    file_name=full_path.name,
                                    key=f"mat_dl_{m['id']}")
                        elif m["kind"] == "link" and m["url"]:
                            st.link_button("🔗 Open link", m["url"])
                    with c2:
                        if parent_mode:
                            if st.button("Remove", key=f"mat_del_{m['id']}"):
                                delete_curriculum_material(int(m["id"]))
                                st.rerun()


def _points_from_visits(visits_df, id_col, name_col):
    """Clean, deduped, numeric lat/lon points ready to plot from a visits df."""
    if visits_df.empty:
        return pd.DataFrame(columns=[id_col, name_col, "lat", "lon"])
    pts = visits_df.dropna(subset=["lat", "lon"]).drop_duplicates(subset=[id_col]).copy()
    pts["lat"] = pd.to_numeric(pts["lat"], errors="coerce")
    pts["lon"] = pd.to_numeric(pts["lon"], errors="coerce")
    return pts.dropna(subset=["lat", "lon"])


def render_travel_map(student_id):
    """Kid-friendly combined map: visited states filled green vs. neutral gray,
    national parks as a 🏔️ snow-capped mountain riding a region-colored circle
    (icon says "what", color says "which region"), cities as a 📍 pin on a
    fixed blue circle. Emoji carry their own vivid color, so the map reads as
    playful rather than a plain data-analyst scatterplot — colors still come
    from the validated dataviz palette, just used as a backdrop instead of
    the whole story."""
    entries = get_travel_entries(student_id)
    visited_states = get_all_visited_states(student_id)
    park_rows = entries[entries["tag_park_id"].notna()].rename(
        columns={"tag_park_id": "park_id", "park_lat": "lat", "park_lon": "lon",
                 "park_region": "region"}) if not entries.empty else entries
    city_rows = entries[entries["tag_city_id"].notna()].rename(
        columns={"tag_city_id": "city_id", "city_lat": "lat", "city_lon": "lon"}) \
        if not entries.empty else entries
    park_pts = _points_from_visits(park_rows, "park_id", "park_name")
    city_pts = _points_from_visits(city_rows, "city_id", "city_name")

    state_df = pd.DataFrame({"state": US_STATES})
    state_df["code"] = state_df["state"].map(US_STATE_ABBR)
    state_df["visited"] = state_df["state"].isin(visited_states).astype(int)

    fig = go.Figure()
    fig.add_trace(go.Choropleth(
        locations=state_df["code"], z=state_df["visited"], locationmode="USA-states",
        colorscale=[[0, MAP_STATE_UNVISITED_COLOR], [1, MAP_STATE_VISITED_COLOR]],
        showscale=False, zmin=0, zmax=1,
        marker_line_color="white", marker_line_width=1.5,
        text=state_df["state"], hovertemplate="%{text}<extra></extra>"))

    def _icon_marker(pts, name_col, color, emoji, legend_name):
        """A colored circle (legend + hover) with an emoji riding on top (no
        legend/hover of its own, so it doesn't create a duplicate entry)."""
        fig.add_trace(go.Scattergeo(
            lon=pts["lon"], lat=pts["lat"], text=pts[name_col],
            mode="markers", name=legend_name,
            marker=dict(size=30, color=color, opacity=0.9,
                       line=dict(width=2, color="white")),
            hovertemplate="%{text}<extra></extra>"))
        fig.add_trace(go.Scattergeo(
            lon=pts["lon"], lat=pts["lat"], mode="text",
            text=[emoji] * len(pts), textfont=dict(size=15),
            showlegend=False, hoverinfo="skip"))

    if not park_pts.empty:
        present_regions = set(park_pts["region"].fillna("Unknown"))
        region_colors = get_region_color_map(present_regions)
        for region, group in park_pts.groupby(park_pts["region"].fillna("Unknown")):
            color = region_colors.get(region, MAP_REGION_MUTED)
            _icon_marker(group, "park_name", color, "🏔️", f"🏔️ {region}")

    if not city_pts.empty:
        _icon_marker(city_pts, "city_name", MAP_CITY_COLOR, "📍", "📍 Cities")

    fig.update_geos(scope="usa", showlakes=True, lakecolor="#dceefb",
                    landcolor="#f7f9fb", bgcolor="rgba(0,0,0,0)")
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=480,
                      legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"),
                      paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)


def render_travel_entry_form(student_id, school_year, key_prefix):
    """Log a travel entry — pick a type, then fill in just that type's own
    fields. A National Park entry only asks about the park (its state is
    implied, so no separate state/city fields); State and City entries are
    likewise their own single picker, not a mix. Every type supports an
    optional photo."""
    st.markdown("**➕ Log a travel entry**")
    parks_df = get_national_parks_df()
    cities_df = get_major_cities_df()
    city_labels = list(cities_df["name"] + " (" + cities_df["state"] + ")")
    city_label_to_id = dict(zip(city_labels, cities_df["id"]))

    entry_type = st.selectbox(
        "Type", ["🏔️ National Park visit", "🗺️ State visit", "🏙️ City visit",
                 "📓 Journal entry"],
        key=f"{key_prefix}_travel_entry_type")

    with st.form(f"{key_prefix}_travel_entry_add", clear_on_submit=True):
        if entry_type == "🏔️ National Park visit":
            c1, c2 = st.columns([2, 1])
            with c1:
                park_name = st.selectbox("Park", list(parks_df["name"]))
            with c2:
                entry_date = st.date_input("Date visited", value=date.today(),
                                           format="MM-DD-YYYY")
            badge = st.checkbox("🏅 Earned Junior Ranger badge")
            st.caption("📝 Where is it, and what's one geographic feature "
                      "(mountains, coast, desert...) that stands out?")
            content = st.text_area("Notes (optional)", height=68,
                                   placeholder="What you did, what you saw...")
        elif entry_type == "🗺️ State visit":
            all_visited = get_all_visited_states(student_id)
            if all_visited:
                st.caption(f"Already covered: {', '.join(sorted(all_visited))}")
            remaining = [s for s in US_STATES if s not in all_visited] or US_STATES
            c1, c2 = st.columns([2, 1])
            with c1:
                state = st.selectbox("State", remaining)
            with c2:
                entry_date = st.date_input("Date (optional)", value=date.today(),
                                           format="MM-DD-YYYY")
            st.caption("📝 What region of the country is this in, and what's "
                      "one geographic feature that stands out?")
            content = st.text_area("Notes (optional)", height=68)
        elif entry_type == "🏙️ City visit":
            c1, c2 = st.columns([2, 1])
            with c1:
                city_label = st.selectbox("City", city_labels)
            with c2:
                entry_date = st.date_input("Date visited", value=date.today(),
                                           format="MM-DD-YYYY")
            st.caption("📝 What's this city's setting like — coast, river, "
                      "mountains, plains?")
            content = st.text_area("Notes (optional)", height=68)
        else:
            title = st.text_input("Title")
            entry_date = st.date_input("Date", value=date.today(),
                                       format="MM-DD-YYYY")
            st.caption("📝 Where were you, and what did you notice about the "
                      "place?")
            content = st.text_area("What happened? What did you see or learn?",
                                   height=120)

        photo = st.file_uploader("Add a photo (optional)",
                                 type=["png", "jpg", "jpeg", "gif", "webp"])

        if st.form_submit_button("Save", type="primary"):
            if entry_type == "📓 Journal entry" and not title.strip():
                st.warning("Give it a title.")
            else:
                photo_path = (save_uploaded_photo(photo, student_id)
                              if photo is not None else None)
                if entry_type == "🏔️ National Park visit":
                    park_id = int(parks_df[parks_df["name"] == park_name].iloc[0]["id"])
                    add_travel_entry(student_id, school_year, entry_date, park_name,
                                     content.strip(), photo_path, None, park_id,
                                     None, badge)
                    st.success(f"Logged {park_name}!")
                elif entry_type == "🗺️ State visit":
                    add_travel_entry(student_id, school_year, entry_date, state,
                                     content.strip(), photo_path, state, None,
                                     None, False)
                    st.success(f"Logged {state}!")
                elif entry_type == "🏙️ City visit":
                    city_id = int(city_label_to_id[city_label])
                    add_travel_entry(student_id, school_year, entry_date, city_label,
                                     content.strip(), photo_path, None, None,
                                     city_id, False)
                    st.success(f"Logged {city_label}!")
                else:
                    add_travel_entry(student_id, school_year, entry_date,
                                     title.strip(), content.strip(), photo_path,
                                     None, None, None, False)
                    st.success("Saved!")
                st.rerun()


def render_travel_entries_list(student_id, key_prefix):
    """One combined, chronological list of every travel entry — parks,
    states, cities, and freeform entries all show up together, distinguished
    by whichever tags/badge they carry."""
    entries = get_travel_entries(student_id)
    if entries.empty:
        st.info("No travel entries logged yet.")
        return

    for _, e in entries.iterrows():
        with st.container(border=True):
            st.markdown(f"**{e['title']}** — {fmt_date(e['entry_date'])}")
            tags = []
            if e["park_name"]:
                tags.append(f"🏔️ {e['park_name']} ({e['park_state']})")
            if e["city_name"]:
                tags.append(f"📍 {e['city_name']} ({e['city_state']})")
            if e["tag_state"]:
                tags.append(f"🗺️ {e['tag_state']}")
            if e["badge_earned"]:
                tags.append("🏅 Junior Ranger badge")
            if tags:
                st.caption(" · ".join(tags))
            if e["content"]:
                st.write(e["content"])
            if e["park_booklet_url"]:
                st.caption(f"[📄 Junior Ranger booklet]({e['park_booklet_url']})")
            if e["photo_path"]:
                photo_full_path = Path(__file__).parent / e["photo_path"]
                if photo_full_path.exists():
                    st.image(str(photo_full_path), width=300)
            if st.button("Remove", key=f"{key_prefix}_travel_entry_del_{e['id']}"):
                delete_travel_entry(int(e["id"]))
                st.rerun()


def render_travel_log(student_id, school_year, key_prefix):
    """Shared Travel Log — used in both Student and Parent views."""
    st.subheader("🗺️ Travel Log")
    st.caption("Track national parks, states, and cities visited — the map "
               "fills in as you go.")

    entries = get_travel_entries(student_id)
    visited_states = get_all_visited_states(student_id)
    total_parks = len(get_national_parks_df())
    total_cities = len(get_major_cities_df())
    park_ct = entries["tag_park_id"].dropna().nunique() if not entries.empty else 0
    city_ct = entries["tag_city_id"].dropna().nunique() if not entries.empty else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("States visited", f"{len(visited_states)}/{len(US_STATES)}",
              f"{100 * len(visited_states) / len(US_STATES):.0f}%")
    c2.metric("Parks visited", f"{park_ct}/{total_parks}",
              f"{100 * park_ct / total_parks:.0f}%" if total_parks else None)
    c3.metric("Cities visited", f"{city_ct}/{total_cities}",
              f"{100 * city_ct / total_cities:.0f}%" if total_cities else None)

    render_travel_map(student_id)

    st.divider()
    with st.expander("📖 Look up a park's Junior Ranger booklet"):
        st.caption("Junior Ranger programs exist at nearly every park — "
                   f"[Become a Junior Ranger]({NPS_JUNIOR_RANGER_LINKS[0]}) · "
                   f"[browse all parks' programs]({NPS_JUNIOR_RANGER_LINKS[1]}).")
        parks_df = get_national_parks_df()
        lookup_name = st.selectbox("Park", list(parks_df["name"]),
                                   key=f"{key_prefix}_park_lookup")
        lookup_row = parks_df[parks_df["name"] == lookup_name].iloc[0]
        if lookup_row["booklet_url"]:
            st.link_button(f"📄 Open {lookup_name}'s Junior Ranger booklet",
                           lookup_row["booklet_url"])
        else:
            st.caption("No booklet link on file for this park.")

    st.divider()
    render_travel_entry_form(student_id, school_year, key_prefix)

    st.divider()
    st.subheader("🧾 All travel entries")
    render_travel_entries_list(student_id, key_prefix)


def render_national_park_pool_admin():
    """Parent-only: manage the master park list (e.g. a newly designated park)."""
    render_pool_admin(
        "Manage park list",
        "Add, edit, or remove parks from the master list. Booklet URL is the "
        "real, park-specific Junior Ranger booklet or program page. Region "
        "is NPS's own regional grouping — drives the map color.",
        get_national_parks_df(), "id",
        [("name", "Name", "text"), ("state", "State", "text"),
         ("lat", "Latitude", "text"), ("lon", "Longitude", "text"),
         ("booklet_url", "Junior Ranger Booklet URL", "text"),
         ("region", "NPS Region", NPS_REGIONS)],
        add_national_park, update_national_park, delete_national_park,
        key_prefix="parkpool")


def render_major_city_pool_admin():
    """Parent-only: manage the master city list."""
    render_pool_admin(
        "Manage city list",
        "Add, edit, or remove cities from the major cities list.",
        get_major_cities_df(), "id",
        [("name", "Name", "text"), ("state", "State", "text"),
         ("lat", "Latitude", "text"), ("lon", "Longitude", "text")],
        add_major_city, update_major_city, delete_major_city,
        key_prefix="citypool",
        expander_label_fn=lambda row: f"{row['name']} ({row['state']})")


def render_proposals_review(student_id, school_year):
    """Parent-only: approve/reject student-submitted elective & book proposals."""
    st.subheader("📮 Student proposals")
    pending = get_proposals(student_id, status="pending")
    if pending.empty:
        st.caption("No pending proposals.")
    else:
        for _, p in pending.iterrows():
            with st.container(border=True):
                st.markdown(f"**{p['title']}** — {p['prop_type'].title()}")
                if p["secondary"]:
                    label = "Resource" if p["prop_type"] == "elective" else "Author"
                    st.caption(f"{label}: {p['secondary']}")
                if p["url"]:
                    st.caption(f"Link: {p['url']}")
                if p["description"]:
                    st.caption(p["description"])
                note = st.text_input("Note (shown to student, esp. if rejecting)",
                                     key=f"prop_note_{p['id']}")
                c1, c2 = st.columns(2)
                with c1:
                    approve = st.button("Approve", key=f"prop_approve_{p['id']}",
                                        type="primary")
                with c2:
                    reject = st.button("Reject", key=f"prop_reject_{p['id']}")
                if approve:
                    if p["prop_type"] == "elective":
                        add_elective_pool_option(p["title"], p["secondary"],
                                                 p["url"], p["description"])
                    else:
                        add_book_pool_option(p["title"], p["secondary"],
                                             p["description"], p["url"])
                    review_proposal(int(p["id"]), "approved", note)
                    st.success("Approved and added to the pool.")
                    st.rerun()
                if reject:
                    review_proposal(int(p["id"]), "rejected", note)
                    st.rerun()

    reviewed = get_proposals(student_id)
    reviewed = (reviewed[reviewed["status"] != "pending"] if not reviewed.empty
               else reviewed)
    if not reviewed.empty:
        with st.expander("Past proposals"):
            st.dataframe(
                reviewed[["title", "prop_type", "status", "parent_note"]].rename(
                    columns={"title": "Title", "prop_type": "Type",
                             "status": "Status", "parent_note": "Note"}),
                use_container_width=True, hide_index=True)


def render_proposals_student(student_id, school_year):
    """Student-only: propose new electives/books, see status of past proposals."""
    st.caption("Suggest an elective or book you want added — a parent will "
               "review it before it shows up as an option.")

    with st.expander("Propose an elective"):
        with st.form("propose_elective", clear_on_submit=True):
            name = st.text_input("Elective name")
            resource = st.text_input("Resource name")
            url = st.text_input("URL")
            desc = st.text_area("What it involves")
            if st.form_submit_button("Submit for approval"):
                if name.strip():
                    add_proposal(student_id, school_year, "elective", name.strip(),
                                 resource.strip(), url.strip(), desc.strip())
                    st.success("Sent to your parent for review!")
                    st.rerun()
                else:
                    st.warning("Give it a name.")

    with st.expander("Propose a book"):
        with st.form("propose_book", clear_on_submit=True):
            title = st.text_input("Book title")
            author = st.text_input("Author")
            url = st.text_input("URL (optional)")
            ties = st.text_area("What it ties to / why you want to read it")
            if st.form_submit_button("Submit for approval"):
                if title.strip():
                    add_proposal(student_id, school_year, "book", title.strip(),
                                 author.strip(), url.strip(), ties.strip())
                    st.success("Sent to your parent for review!")
                    st.rerun()
                else:
                    st.warning("Give it a title.")

    mine = get_proposals(student_id)
    if not mine.empty:
        st.markdown("**Your proposals:**")
        icons = {"pending": "🕓", "approved": "✅", "rejected": "❌"}
        for _, p in mine.iterrows():
            with st.container(border=True):
                st.markdown(f"{icons.get(p['status'], '')} **{p['title']}** "
                            f"({p['prop_type']}) — {p['status'].title()}")
                if p["status"] != "pending" and p["parent_note"]:
                    st.caption(f"Parent note: {p['parent_note']}")

    st.divider()
    done = get_checklist_item(school_year, "propose_done")
    new_done = st.checkbox("✅ I'm done proposing electives & books for now",
                           value=done, key=f"propose_done_{school_year}")
    if new_done != done:
        set_checklist_item(school_year, "propose_done", new_done)
        st.rerun()


def render_launch_checklist(student_id, school_year):
    """Parent-only: pre-school-year readiness checklist, auto + manual items."""
    st.subheader(f"Pre-launch checklist — {school_year}")
    st.caption("Auto-tracked items update themselves from other tabs; check off "
               "the rest as you go.")

    total_items = 0
    done_items = 0

    # --- School year dates
    start_d, end_d = get_school_year_dates(school_year)
    dates_done = start_d is not None and end_d is not None
    total_items += 1
    done_items += int(dates_done)
    with st.container(border=True):
        st.markdown(f"{'✅' if dates_done else '⬜'} **School year start & end "
                    "dates entered**")
        c1, c2 = st.columns(2)
        with c1:
            new_start = st.date_input("Start date", value=start_d or date.today(),
                                      format="MM-DD-YYYY",
                                      key=f"checklist_start_{school_year}")
        with c2:
            new_end = st.date_input(
                "End date", value=end_d or (date.today() + timedelta(days=180)),
                format="MM-DD-YYYY", key=f"checklist_end_{school_year}")
        if st.button("Save dates", key=f"checklist_save_dates_{school_year}"):
            set_school_year_dates(school_year, new_start, new_end)
            st.rerun()

    # --- Holidays / breaks (not counted toward readiness — optional)
    with st.container(border=True):
        st.markdown("**Holidays & breaks**")
        st.caption("Days in these ranges show as a break on the Calendar "
                   "instead of missed school.")
        if st.button("🇺🇸 Add federal holidays for this school year",
                     key=f"seed_fed_holidays_{school_year}"):
            fh_start, fh_end = get_school_year_dates(school_year)
            if not fh_start or not fh_end:
                st.warning("Set the school year start & end dates above first.")
            else:
                added = seed_federal_holidays(school_year, fh_start, fh_end)
                st.success(f"Added {added} federal holiday(s)." if added
                          else "Already up to date — nothing new to add.")
                st.rerun()
        holidays = get_holidays_df(school_year)
        if not holidays.empty:
            for _, h in holidays.iterrows():
                hc1, hc2 = st.columns([5, 1])
                with hc1:
                    st.markdown(f"🎉 **{h['label']}** — {fmt_date(h['start_date'])} "
                               f"to {fmt_date(h['end_date'])}")
                with hc2:
                    if st.button("Remove", key=f"holiday_del_{h['id']}"):
                        delete_holiday(int(h["id"]))
                        st.rerun()
        with st.form(f"holiday_add_{school_year}", clear_on_submit=True):
            hc1, hc2, hc3 = st.columns(3)
            with hc1:
                h_start = st.date_input("Start", value=date.today(),
                                        format="MM-DD-YYYY")
            with hc2:
                h_end = st.date_input("End", value=date.today(),
                                      format="MM-DD-YYYY")
            with hc3:
                h_label = st.text_input("Label (e.g. Winter Break)")
            if st.form_submit_button("Add holiday/break"):
                if h_label.strip() and h_end >= h_start:
                    add_holiday(school_year, h_start, h_end, h_label.strip())
                    st.rerun()
                elif h_end < h_start:
                    st.warning("End date must be on or after the start date.")
                else:
                    st.warning("Give it a label.")

    # --- Electives selected
    electives = get_student_electives(student_id, school_year)
    elect_done = not electives.empty
    total_items += 1
    done_items += int(elect_done)
    with st.container(border=True):
        st.markdown(f"{'✅' if elect_done else '⬜'} **Student elective "
                    "selections submitted**")
        st.caption(("Picked: " + ", ".join(electives["elective_name"])) if elect_done
                  else "Nothing picked yet — set from the Curriculum tab, or have "
                       "him pick in his Electives & Books tab.")

    # --- Reading list started
    books = get_student_books(student_id, school_year)
    books_done = not books.empty
    total_items += 1
    done_items += int(books_done)
    with st.container(border=True):
        st.markdown(f"{'✅' if books_done else '⬜'} **Reading list started**")
        st.caption(f"{len(books)} book(s) on the list." if books_done
                  else "No books added yet.")

    # --- Logins created
    accts = get_accounts(student_id)
    applicable_services = get_applicable_account_services(student_id, school_year)
    created_ct = (accts[(accts["status"] == "created")
                        & (accts["service_name"].isin(applicable_services))]
                  ["service_name"].nunique() if not accts.empty else 0)
    needed_ct = len(applicable_services)
    logins_done = created_ct >= needed_ct
    total_items += 1
    done_items += int(logins_done)
    with st.container(border=True):
        st.markdown(f"{'✅' if logins_done else '⬜'} **Logins created for "
                    f"curriculum sites** ({created_ct}/{needed_ct})")
        st.caption("Set these up in the Accounts tab.")

    # --- Manual items
    for item in MANUAL_CHECKLIST_ITEMS:
        checked = get_checklist_item(school_year, item["key"])
        total_items += 1
        done_items += int(checked)
        with st.container(border=True):
            new_val = st.checkbox(item["label"], value=checked,
                                  key=f"checklist_{item['key']}_{school_year}")
            st.caption(item["help"])
            if new_val != checked:
                set_checklist_item(school_year, item["key"], new_val)
                st.rerun()

    st.divider()
    st.progress(done_items / total_items,
                text=f"{done_items} / {total_items} ready for launch")
    if done_items == total_items:
        st.success("🎉 Everything's checked off — ready for day one!")


def render_accounts_checklist(student_id, school_year):
    """Parent-only: checklist of sites that need a login, with fields to save one."""
    st.subheader("Accounts checklist")
    st.caption("Every site the curriculum & electives link to. Check it off once an "
               "account exists and save the login here — he'll see it in his 🔑 My "
               "Logins tab. Elective-only sites appear once that elective is picked.")
    st.caption("⚠️ Stored as plain text in the local database (same as everything "
               "else in this app) so he can read it to log in himself. Don't reuse "
               "a password here that matters elsewhere.")
    existing = get_accounts(student_id)
    by_service = {r["service_name"]: r for _, r in existing.iterrows()} \
        if not existing.empty else {}
    applicable = get_applicable_account_services(student_id, school_year)
    required_services = {n: i for n, i in applicable.items() if i["required"]}
    elective_services = {n: i for n, i in applicable.items() if not i["required"]}

    def _service_row(service, info):
        row = by_service.get(service)
        is_created = row is not None and row["status"] == "created"
        with st.container(border=True):
            st.markdown(f"{'✅' if is_created else '⬜'} **[{service}]({info['url']})**")
            st.caption(info["tie"])
            with st.form(key=f"acct_{service}"):
                c1, c2, c3, c4 = st.columns([2, 2, 1.5, 1])
                with c1:
                    u = st.text_input("Username", key=f"acct_u_{service}",
                                      value=row["username"] if row is not None
                                      and row["username"] else "")
                with c2:
                    p = st.text_input("Password", key=f"acct_p_{service}",
                                      value=row["password"] if row is not None
                                      and row["password"] else "")
                with c3:
                    cc = st.text_input("Class code", key=f"acct_cc_{service}",
                                       value=row["class_code"] if row is not None
                                       and row["class_code"] else "",
                                       help="If this site makes you create a "
                                            "class and join it with a code, "
                                            "keep the code here.")
                with c4:
                    created = st.checkbox("Created", value=is_created,
                                          key=f"acct_c_{service}")
                if st.form_submit_button("Save"):
                    upsert_account(student_id, service, info["url"], u, p,
                                   "created" if created else "not_started",
                                   cc.strip() or None)
                    st.rerun()
        return is_created

    created_ct = 0
    st.markdown("**Required**")
    for service, info in required_services.items():
        created_ct += int(_service_row(service, info))

    st.markdown("**Electives** (based on current picks)")
    if elective_services:
        for service, info in elective_services.items():
            created_ct += int(_service_row(service, info))
    else:
        st.caption("No electives picked yet — pick some in the Curriculum tab "
                   "to see their logins here.")

    st.progress(created_ct / len(applicable) if applicable else 0,
                text=f"{created_ct} / {len(applicable)} accounts set up")

    st.divider()
    st.subheader("Add a custom account")
    st.caption("For anything outside the curriculum list — library card, district "
               "portal, WAVA/CVA login, etc.")
    with st.form("acct_custom", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            cs_name = st.text_input("Service name")
            cs_url = st.text_input("URL")
        with c2:
            cs_user = st.text_input("Username", key="acct_custom_user")
            cs_pw = st.text_input("Password", key="acct_custom_pw")
        cs_cc = st.text_input("Class code (optional)", key="acct_custom_cc")
        if st.form_submit_button("Add"):
            if cs_name.strip():
                upsert_account(student_id, cs_name.strip(), cs_url.strip(),
                               cs_user, cs_pw, "created",
                               cs_cc.strip() or None)
                st.success("Added.")
                st.rerun()
            else:
                st.warning("Give it a name.")

    custom = existing[~existing["service_name"].isin(ACCOUNT_SERVICES.keys())] \
        if not existing.empty else existing
    if not custom.empty:
        st.markdown("**Custom accounts:**")
        for _, r in custom.iterrows():
            with st.container(border=True):
                cc1, cc2 = st.columns([5, 1])
                with cc1:
                    code_bit = (f" · Class code: `{r['class_code']}`"
                                if r["class_code"] else "")
                    st.markdown(f"**{r['service_name']}** — {r['url']}  \n"
                                f"Username: `{r['username']}` · "
                                f"Password: `{r['password']}`{code_bit}")
                with cc2:
                    if st.button("Remove", key=f"acct_del_{r['id']}"):
                        delete_account(int(r["id"]))
                        st.rerun()

    st.divider()
    st.subheader("🔗 Broken link reports")
    st.caption("Links he's flagged as dead or broken while using the app.")
    pending = get_link_reports(student_id, status="pending")
    if pending.empty:
        st.caption("No pending reports.")
    else:
        for _, r in pending.iterrows():
            with st.container(border=True):
                st.markdown(f"**{r['url']}**  \n_reported {fmt_date(r['report_date'])}_")
                if r["description"]:
                    st.caption(r["description"])
                note = st.text_input("Note (optional)", key=f"link_note_{r['id']}")
                bc1, bc2, bc3 = st.columns(3)
                with bc1:
                    if st.button("✅ Mark fixed", key=f"link_fixed_{r['id']}"):
                        update_link_report(int(r["id"]), "fixed", note.strip())
                        st.rerun()
                with bc2:
                    if st.button("❌ Dismiss", key=f"link_dismiss_{r['id']}"):
                        update_link_report(int(r["id"]), "dismissed", note.strip())
                        st.rerun()
                with bc3:
                    if st.button("🗑️ Delete", key=f"link_del_{r['id']}"):
                        delete_link_report(int(r["id"]))
                        st.rerun()

    resolved = get_link_reports(student_id)
    resolved = resolved[resolved["status"] != "pending"] if not resolved.empty else resolved
    if not resolved.empty:
        with st.expander(f"Resolved ({len(resolved)})"):
            icons = {"fixed": "✅", "dismissed": "❌"}
            for _, r in resolved.iterrows():
                st.markdown(f"{icons.get(r['status'], '')} {r['url']} — {r['status'].title()}")
                if r["parent_note"]:
                    st.caption(f"Note: {r['parent_note']}")


def render_accounts_table(student_id):
    """Student-only: read-only table of saved logins."""
    st.subheader("My logins")
    accts = get_accounts(student_id)
    accts = accts[accts["status"] == "created"] if not accts.empty else accts
    if accts.empty:
        st.info("No logins saved yet — ask a parent to set them up in Parent mode.")
    else:
        show = accts[["service_name", "url", "username", "password",
                      "class_code"]].rename(columns={
            "service_name": "Service", "url": "URL", "username": "Username",
            "password": "Password", "class_code": "Class code"})
        show["Class code"] = show["Class code"].fillna("")
        st.dataframe(show, use_container_width=True, hide_index=True,
                    column_config={"URL": st.column_config.LinkColumn("URL")})
        if show["Class code"].str.strip().ne("").any():
            st.caption("Class code is what you enter on the site to join the "
                       "class your parent set up.")

    st.divider()
    st.subheader("🔗 Report a broken link")
    st.caption("Found a link anywhere in the app that doesn't work? Let a "
               "parent know so they can fix it.")
    with st.form("link_report_add", clear_on_submit=True):
        report_url = st.text_input("The broken link (or where you found it)")
        report_desc = st.text_area("What's wrong?", height=68,
                                   placeholder="e.g. 404 error, wrong page, etc.")
        if st.form_submit_button("Report it", type="primary"):
            if report_url.strip():
                add_link_report(student_id, report_url.strip(), report_desc.strip())
                st.success("Sent to your parent!")
                st.rerun()
            else:
                st.warning("Paste the link (or describe where it is).")

    my_reports = get_link_reports(student_id)
    if not my_reports.empty:
        st.markdown("**Your reports:**")
        icons = {"pending": "🕓", "fixed": "✅", "dismissed": "❌"}
        for _, r in my_reports.iterrows():
            st.markdown(f"{icons.get(r['status'], '')} {r['url']} — "
                       f"{r['status'].title()}")
            if r["status"] != "pending" and r["parent_note"]:
                st.caption(f"Parent note: {r['parent_note']}")


def _week_habit_grid(student_id, today):
    """Renders a Mon-Sun row of habit-completion icons for the current week."""
    week_start = today - timedelta(days=today.weekday())
    week_df = get_health_habits_range(student_id, week_start,
                                      week_start + timedelta(days=6))
    by_date = {r["log_date"]: r for _, r in week_df.iterrows()} if not week_df.empty else {}
    cols = st.columns(7)
    for i in range(7):
        d = week_start + timedelta(days=i)
        row = by_date.get(d.isoformat())
        done_ct = sum(row[h["key"]] for h in HEALTH_HABITS) if row is not None else 0
        if done_ct == len(HEALTH_HABITS):
            icon = "✅"
        elif done_ct > 0:
            icon = "🟡"
        elif d > today:
            icon = "⬛"
        else:
            icon = "▫️"
        with cols[i]:
            st.markdown(f"<div style='text-align:center'>"
                       f"<div style='font-size:0.75em'>{d.strftime('%a')}</div>"
                       f"<div style='font-size:1.1em'>{icon}</div></div>",
                       unsafe_allow_html=True)


def render_health_habits_checkin(student_id):
    """Student-only: the end-of-day debrief card on the Today tab. Returns True
    once it counts as done (see debrief_is_done) so Today can treat it as a
    checklist item.

    Built for a 13-year-old, which drives every choice here: two taps to
    "done", chips instead of a text box, honesty rewarded over performance,
    and the typing kept optional and out of the way at the bottom.
    """
    today = date.today()
    h = get_health_habits_day(student_id, today)
    is_done = debrief_is_done(h)
    with st.container(border=True):
        st.markdown(f"{'✅' if is_done else '⬜'} **⚡ Daily Debrief**")
        st.caption("Two taps and you're done. Nobody's grading this — it's "
                   "only useful if it's honest.")

        rc1, rc2 = st.columns(2)
        with rc1:
            st.caption("How are **you** doing?")
            mood_pick = st.radio(
                "Mood rating", RATING_SCALE, horizontal=True,
                index=(h["mood_rating"] - 1) if h["mood_rating"] else None,
                key=f"health_mood_rating_{today.isoformat()}",
                label_visibility="collapsed")
            if mood_pick is not None:
                new_val = RATING_SCALE.index(mood_pick) + 1
                if new_val != h["mood_rating"]:
                    set_health_rating(student_id, today, "mood_rating", new_val)
                    st.rerun()
        with rc2:
            st.caption("How'd the **schoolwork** go?")
            lesson_pick = st.radio(
                "Lesson score", RATING_SCALE, horizontal=True,
                index=(h["lesson_score"] - 1) if h["lesson_score"] else None,
                key=f"health_lesson_score_{today.isoformat()}",
                label_visibility="collapsed")
            new_score = (RATING_SCALE.index(lesson_pick) + 1
                         if lesson_pick is not None else None)
            if new_score != h["lesson_score"]:
                set_lesson_reflection(student_id, today, new_score,
                                      h["lesson_feedback"])
                st.rerun()

        st.caption("Anything get in the way? Tap what fits — or don't, "
                   "if it was all fine.")
        picked = st.pills("Friction", FRICTION_TAGS, selection_mode="multi",
                          default=h["friction_tags"],
                          key=f"health_friction_{today.isoformat()}",
                          label_visibility="collapsed")
        picked = picked or []
        gripes = [t for t in picked if t != POSITIVE_FRICTION_TAG]
        # Only ask which subject once he's said something actually went wrong —
        # no point asking "what was roughest?" about a day he says was fine.
        rough = h["rough_subject"]
        if gripes:
            opts = ["—"] + WA_SUBJECTS + ["Electives"]
            rough_pick = st.selectbox(
                "Which one was the worst of it?", opts,
                index=opts.index(rough) if rough in opts else 0,
                key=f"health_rough_{today.isoformat()}")
            rough = "" if rough_pick == "—" else rough_pick
        else:
            rough = ""
        if picked != h["friction_tags"] or rough != h["rough_subject"]:
            set_friction(student_id, today, picked, rough)
            st.rerun()

        move = get_daily_move(today)
        mv1, mv2 = st.columns([3, 1])
        with mv1:
            st.markdown(f"**Today's move:** {move}")
        with mv2:
            move_done = st.checkbox("Did it 💥", value=bool(h["daily_move"]),
                                    key=f"health_move_{today.isoformat()}")
            if move_done != bool(h["daily_move"]):
                set_daily_move(student_id, today, move_done)
                st.rerun()

        st.caption("Basics — tick what's actually true:")
        cols = st.columns(len(HEALTH_HABITS))
        for i, hb in enumerate(HEALTH_HABITS):
            with cols[i]:
                checked = st.checkbox(
                    f"{hb['emoji']} {hb['label']}", value=bool(h[hb["key"]]),
                    key=f"health_{hb['key']}_{today.isoformat()}")
                if checked != bool(h[hb["key"]]):
                    set_health_habit(student_id, today, hb["key"], checked)
                    st.rerun()

        streak = get_health_streak(student_id)
        if streak > 0:
            st.success(f"🔥 {streak}-day streak — you've checked in "
                       f"{streak} day{'s' if streak != 1 else ''} running.")

        with st.expander("📓 Journal (optional)"):
            journal_text = st.text_area(
                "Journal", value=h["journal"],
                key=f"health_journal_{today.isoformat()}",
                label_visibility="collapsed",
                placeholder="Anything on your mind. Nobody reads this but you "
                            "and your parent.", height=100)
            if journal_text != h["journal"]:
                set_health_journal(student_id, today, journal_text)
    return is_done


def render_health_habits_summary(student_id):
    """Parent-only: read-only weekly view of his Daily Debrief."""
    st.subheader("⚡ Daily Debrief")
    st.caption("What he logs himself at the end of each day — how he's doing, "
               "how the schoolwork landed, what got in the way, the basics, "
               "and an optional journal. Separate from Health coursework hours.")
    week_df = get_health_habits_range(student_id, date.today() - timedelta(days=6),
                                      date.today())
    streak = get_health_streak(student_id)
    m1, m2, m3 = st.columns(3)
    m1.metric("Check-in streak", f"{streak} day{'s' if streak != 1 else ''}",
              help="Consecutive days he filled the debrief in at all — this "
                   "counts showing up, not doing everything right.")

    def _avg_metric(col, label, field, help_text):
        vals = week_df[field].dropna() if not week_df.empty else pd.Series(dtype=float)
        if vals.empty:
            col.metric(label, "—")
        else:
            avg = vals.mean()
            col.metric(label, f"{RATING_SCALE[min(int(round(avg)) - 1, 4)]} {avg:.1f}/5",
                       help=help_text)

    _avg_metric(m2, "How he's doing (7-day)", "mood_rating",
                "Average of his daily \"How are you doing?\" rating.")
    _avg_metric(m3, "Schoolwork (7-day)", "lesson_score",
                "Average of his daily \"How'd the schoolwork go?\" rating.")

    # The friction chips are the point of the whole redesign: one tap from him,
    # but counted across a week they say "Math has been confusing 3 times",
    # which is something you can actually act on. Prose never aggregated.
    if not week_df.empty:
        tally = {}
        for tags in week_df["friction_tags"].fillna(""):
            for t in [x for x in tags.split(",") if x]:
                tally[t] = tally.get(t, 0) + 1
        if tally:
            st.markdown("**What got in the way this week**")
            st.markdown("  ".join(
                f"{tag} ×{n}" for tag, n in
                sorted(tally.items(), key=lambda kv: -kv[1])))
            rough = week_df["rough_subject"].fillna("")
            rough = rough[rough.str.strip().ne("")]
            if not rough.empty:
                counts = rough.value_counts()
                st.caption("Roughest subject: " + ", ".join(
                    f"{s} ×{n}" for s, n in counts.items()))

    st.caption("Habit boxes he ticked, Mon–Sun — ✅ all four · 🟡 some · "
               "▫️ none · ⬛ not here yet")
    _week_habit_grid(student_id, date.today())

    has_content = (week_df["journal"].fillna("").str.strip().ne("")
                  | week_df["mood_rating"].notna()
                  | week_df["lesson_score"].notna()
                  | week_df["friction_tags"].fillna("").str.strip().ne("")
                  | week_df["lesson_feedback"].fillna("").str.strip().ne("")
                  ) if not week_df.empty else pd.Series(dtype=bool)
    entries = week_df[has_content] if not week_df.empty else week_df
    if not entries.empty:
        with st.expander("Day by day"):
            for _, r in entries.sort_values("log_date", ascending=False).iterrows():
                mood_e = RATING_SCALE[int(r["mood_rating"]) - 1] if pd.notna(r["mood_rating"]) else "—"
                lesson_e = (RATING_SCALE[int(r["lesson_score"]) - 1]
                            if pd.notna(r["lesson_score"]) else "—")
                st.markdown(f"**{fmt_date(r['log_date'])}** · Him: {mood_e} · "
                            f"Schoolwork: {lesson_e}")
                tags = [t for t in (r["friction_tags"] or "").split(",") if t]
                if tags:
                    line = "  ".join(tags)
                    if r["rough_subject"]:
                        line += f"  — worst: **{r['rough_subject']}**"
                    st.caption(line)
                if r["lesson_feedback"] and str(r["lesson_feedback"]).strip():
                    st.caption(f"🧩 In his words: {r['lesson_feedback']}")
                if r["journal"] and r["journal"].strip():
                    st.caption(f"📓 {r['journal']}")
    else:
        st.caption("No check-in details this week yet.")


def render_support_resources(student_id):
    """Parent-only: check-in log + reminder, and curated support resources.
    Private to Parent mode — Landon doesn't see this tab or its contents."""
    st.subheader("🧠 Support & Check-ins")
    st.caption("A place to jot how he's actually doing, separate from his "
               "own daily habit check-in, plus a few reputable resources.")

    reminder = get_checkin_reminder(student_id)
    if reminder:
        st.info(f"💬 {reminder}")

    with st.form("parent_checkin_add", clear_on_submit=True):
        c1, c2 = st.columns([1, 3])
        with c1:
            ci_date = st.date_input("Date", value=date.today(), format="MM-DD-YYYY")
        with c2:
            ci_notes = st.text_area("Notes", height=80,
                                    placeholder="How's he seeming lately? "
                                    "Anything worth remembering?")
        if st.form_submit_button("Log check-in", type="primary"):
            add_parent_checkin(student_id, ci_date, ci_notes.strip())
            st.rerun()

    hist = get_parent_checkins(student_id)
    if not hist.empty:
        with st.expander(f"Past check-ins ({len(hist)})"):
            for _, r in hist.iterrows():
                cc1, cc2 = st.columns([5, 1])
                with cc1:
                    st.markdown(f"**{fmt_date(r['checkin_date'])}**")
                    if r["notes"]:
                        st.caption(r["notes"])
                with cc2:
                    if st.button("Remove", key=f"checkin_del_{r['id']}"):
                        delete_parent_checkin(int(r["id"]))
                        st.rerun()

    with st.expander("📚 Helpful resources"):
        st.markdown(
            "**Autism / neurodiversity**\n"
            "- [Autism Society](https://autismsociety.org/) — general info, "
            "local chapter finder, family support.\n"
            "- [Autistic Self Advocacy Network](https://autisticadvocacy.org/) "
            "— run by autistic people; good for firsthand perspective, not "
            "just clinical framing.\n\n"
            "**Mental health**\n"
            "- [Child Mind Institute](https://childmind.org/) — clear, "
            "practical guides for parents on anxiety, focus, mood, and more.\n"
            "- [NAMI](https://www.nami.org/) — National Alliance on Mental "
            "Illness; education and family support programs.\n"
            "- [988 Suicide & Crisis Lifeline](https://988lifeline.org/) — "
            "call or text **988** anytime, for him or for you. Free and "
            "confidential.\n\n"
            "None of this is a diagnosis or a substitute for a real "
            "conversation with his pediatrician if something feels off — "
            "just a starting point.")


def render_day1_checklist(student_id, school_year):
    """Student-only: Day 1 & Day 2 orientation checklist."""
    st.subheader("Day 1 & Day 2 Checklist")
    st.caption("Get set up before you dive into lessons. Ask a parent if you get stuck.")

    school_email = get_school_email(student_id)
    if school_email:
        st.info(f"📧 Use this email for all your school site signups: "
                f"**{school_email}**")
    else:
        st.warning("No school email found yet — ask a parent to add your "
                   "Google/Gmail account in the 🔑 Accounts tab first.")

    school_start, _ = get_school_year_dates(school_year)
    day2_unlock = (school_start + timedelta(days=1)) if school_start else None
    day2_locked = day2_unlock is not None and date.today() < day2_unlock

    total_items = 0
    done_items = 0

    st.markdown("## Day 1")

    # --- Logins
    accts = get_accounts(student_id)
    applicable_services = get_applicable_account_services(student_id, school_year)
    created_ct = (accts[(accts["status"] == "created")
                        & (accts["service_name"].isin(applicable_services))]
                  ["service_name"].nunique() if not accts.empty else 0)
    needed_ct = len(applicable_services)
    logins_done = created_ct >= needed_ct
    total_items += 1
    done_items += int(logins_done)
    with st.container(border=True):
        st.markdown(f"{'✅' if logins_done else '⬜'} **Logins created for "
                    f"curriculum sites** ({created_ct}/{needed_ct})")
        by_service = ({r["service_name"]: r for _, r in accts.iterrows()}
                      if not accts.empty else {})
        if school_email:
            st.markdown(f"✅ Google/Gmail — done ({school_email})")

        def _quick_row(service, info):
            row = by_service.get(service)
            is_created = row is not None and row["status"] == "created"
            if is_created:
                st.markdown(f"✅ {service} — done")
            else:
                hint = (f" Sign up with **{school_email}**." if school_email
                       else " Ask a parent for your school email first.")
                st.markdown(f"⬜ [{service}]({info['url']}) — {info['tie']}.{hint}")

        st.markdown("**Required:**")
        for service, info in applicable_services.items():
            if info["required"]:
                _quick_row(service, info)

        elective_only = {n: i for n, i in applicable_services.items()
                         if not i["required"]}
        if elective_only:
            st.markdown("**For your electives:**")
            for service, info in elective_only.items():
                _quick_row(service, info)

        st.caption("Once you sign up, tell a parent your login so they can "
                   "save it in Parent mode — it'll show up here and in your "
                   "🔑 My Logins tab.")

    # --- Propose electives & books
    proposals = get_proposals(student_id)
    propose_done = get_checklist_item(school_year, "propose_done")
    total_items += 1
    done_items += int(propose_done)
    with st.container(border=True):
        st.markdown(f"{'✅' if propose_done else '⬜'} **Propose electives "
                    "& books you want**")
        if not proposals.empty:
            st.caption(f"You've submitted {len(proposals)} proposal(s). Check "
                      "\"I'm done proposing\" in the 🎯 Electives & Books tab "
                      "once you're finished.")
        else:
            st.caption(
                "Suggest an elective or book in the 🎯 Electives & Books tab — a "
                "parent reviews it overnight so it's ready to officially pick "
                "from on Day 2.")

    st.markdown("## Day 2")

    # --- Electives
    electives = get_student_electives(student_id, school_year)
    elect_done = not electives.empty
    total_items += 1
    done_items += int(elect_done)
    with st.container(border=True):
        if day2_locked:
            st.markdown("🔒 **Select your electives for the year**")
            st.caption(f"Unlocks {fmt_date(day2_unlock)} — finish "
                       "Day 1 first.")
        else:
            st.markdown(f"{'✅' if elect_done else '⬜'} **Electives picked "
                        "for the year**")
            st.caption(("Picked: " + ", ".join(electives["elective_name"]))
                      if elect_done else
                      "Pick yours in the 🎯 Electives & Books tab.")

    # --- Reading list
    books = get_student_books(student_id, school_year)
    books_done = not books.empty
    total_items += 1
    done_items += int(books_done)
    with st.container(border=True):
        if day2_locked:
            st.markdown("🔒 **Build your reading list**")
            st.caption(f"Unlocks {fmt_date(day2_unlock)}, same as "
                       "electives.")
        else:
            st.markdown(f"{'✅' if books_done else '⬜'} **At least one book "
                        "on your reading list**")
            st.caption(f"{len(books)} book(s) on your list." if books_done
                      else "Add one in the 🎯 Electives & Books tab.")

    # --- Manual orientation items
    for item in DAY1_MANUAL_ITEMS:
        checked = get_checklist_item(school_year, item["key"])
        total_items += 1
        done_items += int(checked)
        with st.container(border=True):
            new_val = st.checkbox(item["label"], value=checked,
                                  key=f"{item['key']}_{school_year}")
            st.caption(item["help"])
            if new_val != checked:
                set_checklist_item(school_year, item["key"], new_val)
                st.rerun()

    st.divider()
    st.progress(done_items / total_items, text=f"{done_items} / {total_items} ready to go")
    if done_items == total_items:
        st.success("🎉 You're all set!")


# ------------------------------------------------------------- app shell
st.set_page_config(page_title=APP_NAME, page_icon="🧭", layout="wide")

# Comic Log — applied app-wide so every bordered panel (Today's blocks, the
# Current Quest card, etc.) reads as a comic panel, not just the Quest Board
# cards. Targets Streamlit's own bordered-container test id; a defensive,
# best-effort selector — if a future Streamlit version renames it, this
# rule just silently no-ops rather than breaking anything.
st.markdown("""
<style>
/* Solid Pop — one bold flat color for the main page (set via
   backgroundColor in config.toml), with the sidebar in a contrasting
   flat color so the two regions read as distinct. */
[data-testid="stSidebar"] {
    background-color: #4FC3E8;
    background-image: none;
}
[data-testid="stVerticalBlockBorderWrapper"] > div {
    border: 3px solid #1A1610 !important;
    border-radius: 8px !important;
    box-shadow: 4px 4px 0 #1A161033;
    background: #FFFDF6;
}
button[kind="primary"], button[kind="secondary"] {
    border: 2px solid #1A1610 !important;
    box-shadow: 2px 2px 0 #1A1610;
    font-weight: 700 !important;
}
button[kind="primary"]:hover, button[kind="secondary"]:hover {
    transform: translate(-1px, -1px);
    box-shadow: 3px 3px 0 #1A1610;
}
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [aria-selected="true"] { font-weight: 800 !important; }

/* Student nav — Always-On Color: every button in a group carries a pale
   tint of that group's color at rest, and goes full-saturated with an
   outline when it's the active view. Scoped via st.container(key=...),
   which Streamlit renders as a stable "st-key-<name>" class. */
.st-key-nav_schedule button[kind="secondary"] { background: #BEE7F7 !important; color: #1A1610 !important; }
.st-key-nav_schedule button[kind="primary"] { background: #4FC3E8 !important; color: #1A1610 !important; outline: 2px solid #1A1610; outline-offset: 1px; }
.st-key-nav_learning button[kind="secondary"] { background: #CFF0D3 !important; color: #1A1610 !important; }
.st-key-nav_learning button[kind="primary"] { background: #6FCF7A !important; color: #1A1610 !important; outline: 2px solid #1A1610; outline-offset: 1px; }
.st-key-nav_extras button[kind="secondary"] { background: #FCD3E6 !important; color: #1A1610 !important; }
.st-key-nav_extras button[kind="primary"] { background: #FF5FA2 !important; color: #1A1610 !important; outline: 2px solid #1A1610; outline-offset: 1px; }
.st-key-nav_more button[kind="secondary"] { background: #E3D3F9 !important; color: #1A1610 !important; }
.st-key-nav_more button[kind="primary"] { background: #B084F0 !important; color: #1A1610 !important; outline: 2px solid #1A1610; outline-offset: 1px; }
/* Parent nav — same Always-On Color treatment, one color per group. */
.st-key-pnav_daily button[kind="secondary"] { background: #BEE7F7 !important; color: #1A1610 !important; }
.st-key-pnav_daily button[kind="primary"] { background: #4FC3E8 !important; color: #1A1610 !important; outline: 2px solid #1A1610; outline-offset: 1px; }
.st-key-pnav_progress button[kind="secondary"] { background: #CFF0D3 !important; color: #1A1610 !important; }
.st-key-pnav_progress button[kind="primary"] { background: #6FCF7A !important; color: #1A1610 !important; outline: 2px solid #1A1610; outline-offset: 1px; }
.st-key-pnav_content button[kind="secondary"] { background: #FCE9C7 !important; color: #1A1610 !important; }
.st-key-pnav_content button[kind="primary"] { background: #F5B841 !important; color: #1A1610 !important; outline: 2px solid #1A1610; outline-offset: 1px; }
.st-key-pnav_records button[kind="secondary"] { background: #FCD3E6 !important; color: #1A1610 !important; }
.st-key-pnav_records button[kind="primary"] { background: #FF5FA2 !important; color: #1A1610 !important; outline: 2px solid #1A1610; outline-offset: 1px; }
.st-key-pnav_setup button[kind="secondary"] { background: #E3D3F9 !important; color: #1A1610 !important; }
.st-key-pnav_setup button[kind="primary"] { background: #B084F0 !important; color: #1A1610 !important; outline: 2px solid #1A1610; outline-offset: 1px; }
[data-testid="stSidebar"] .stButton button { margin-bottom: 2px; }
</style>
""", unsafe_allow_html=True)

students_df = get_students()

with st.sidebar:
    st.markdown(
        '<div style="border:3px solid #1A1610;border-radius:8px;padding:10px 14px;'
        'margin-bottom:8px;background:linear-gradient(135deg,#FFD23F,#FF9F45);'
        'box-shadow:4px 4px 0 #1A1610">'
        '<span style="font-size:22px;font-weight:900;color:#1A1610;'
        f'font-style:italic">🧭 {APP_NAME}</span></div>',
        unsafe_allow_html=True)
    # Parent mode is only offered to whoever's on this Mac itself
    # (localhost) — devices reached over the LAN address (Landon's
    # laptop/phone) see Student mode only, no toggle at all.
    client_ip = st.context.ip_address
    is_local = client_ip in (None, "127.0.0.1", "::1", "localhost")
    # A link from the Parent Console ("Open Student View") opens a new tab
    # at ?view=student — force Student mode there even on localhost, so it
    # always lands cleanly instead of showing the mode toggle.
    force_student = st.query_params.get("view") == "student"
    if is_local and not force_student:
        # This Mac is the parent's launch point, so default to Parent mode
        # on load rather than Student.
        mode = st.radio("Mode", ["🔑 Parent", "🎒 Student"], label_visibility="collapsed")
    else:
        mode = "🎒 Student"

    if mode == "🎒 Student":
        st.caption("Student View")

    st.divider()
    # --- student picker
    if not students_df.empty:
        names = students_df["name"] + " (" + students_df["grade"].fillna("") + ")"
        idx = st.selectbox("Student", range(len(students_df)),
                           format_func=lambda i: names.iloc[i])
        student_id = int(students_df.iloc[idx]["id"])
        student_row = students_df.iloc[idx]
    else:
        student_id = None
        student_row = None
        st.info("No student yet — add one in Parent mode.")

    # Shared grouped-button sidebar nav, used by both Student and Parent
    # modes. state_key is the st.session_state field the group drives
    # ("student_view" or "parent_view"), so the two navs stay independent.
    def _nav_group(label, items, key, state_key):
        st.markdown(f'<div style="font-size:13px;font-weight:900;letter-spacing:.06em;'
                   f'text-transform:uppercase;color:#1A1610;margin:12px 0 6px">{label}</div>',
                   unsafe_allow_html=True)
        with st.container(key=key):
            for view_label, icon in items:
                is_on = st.session_state[state_key] == view_label
                if st.button(f"{icon} {view_label}", key=f"{key}_{view_label}",
                            use_container_width=True,
                            type="primary" if is_on else "secondary"):
                    st.session_state[state_key] = view_label
                    st.rerun()

    if mode == "🎒 Student":
        if "student_view" not in st.session_state:
            st.session_state.student_view = "Today"

        _nav_group("📅 Schedule & Quests", [
            ("Today", "📅"), ("My Plan", "🧭"), ("My Week", "🗓"), ("Calendar", "📆"),
            ("Passion Track", "🗺️")],
            "nav_schedule", "student_view")
        _nav_group("🎯 Learning", [
            ("Foundations", "🧭"), ("Electives & Books", "🎯"), ("Quizzes", "📝"),
            ("My Grades", "🏆")],
            "nav_learning", "student_view")
        _nav_group("🧳 Extras", [
            ("Travel Log", "🧳"), ("Resources", "📎")],
            "nav_extras", "student_view")
        _nav_group("⋯ More", [
            ("Day 1 Checklist", "🚀"), ("8th Grade Scope", "📋"), ("My Logins", "🔑")],
            "nav_more", "student_view")

    if mode == "🔑 Parent":
        if "parent_view" not in st.session_state:
            st.session_state.parent_view = "Review & Approve"

        _nav_group("📅 Daily Work", [
            ("Review & Approve", "🕓"), ("Manual Log", "📝"), ("Grading", "🎓")],
            "pnav_daily", "parent_view")
        _nav_group("📊 Progress", [
            ("Dashboard", "📊"), ("Curriculum", "📚"), ("8th Grade Scope", "📋")],
            "pnav_progress", "parent_view")
        _nav_group("🎯 Content", [
            ("Plan Blender", "🎛️"), ("Passion Track", "🗺️"), ("Foundations", "🧭"),
            ("Travel Log", "🧳")],
            "pnav_content", "parent_view")
        _nav_group("🗄️ Records", [
            ("Accounts", "🔑"), ("Assessments", "✅"), ("Export", "⬇️")],
            "pnav_records", "parent_view")
        _nav_group("⚙️ Setup", [
            ("Launch Checklist", "🚀"), ("Settings", "⚙️"), ("Resources", "📎")],
            "pnav_setup", "parent_view")

        with st.expander("➕ Add a student"):
            n = st.text_input("Name", key="add_name")
            g = st.text_input("Grade (e.g. 8th)", key="add_grade")
            y = st.text_input("School year (e.g. 2026-2027)", key="add_year")
            if st.button("Add"):
                if n.strip():
                    conn.execute("INSERT INTO students (name, grade, school_year) "
                                 "VALUES (?, ?, ?)", (n.strip(), g.strip(), y.strip()))
                    conn.commit()
                    st.rerun()

parent_mode = (mode == "🔑 Parent")

# =========================================================== STUDENT MODE
if not parent_mode:
    if student_id is None:
        st.stop()
    st.title(f"Hi {student_row['name']}! 👋")

    _unseen_materials = get_curriculum_materials()
    _unseen_materials = _unseen_materials[_unseen_materials["seen"] == 0] \
        if not _unseen_materials.empty else _unseen_materials
    if not _unseen_materials.empty:
        n = len(_unseen_materials)
        st.warning(f"📎 {n} new resource{'s' if n != 1 else ''} added for you — "
                   "check them out below.")
        with st.expander("See what's new", expanded=True):
            for _, m in _unseen_materials.iterrows():
                st.markdown(f"**{m['title']}** ({m['subject'] or 'Uncategorized'})")
                if m["notes"]:
                    st.caption(m["notes"])
            if st.button("Got it — mark as seen"):
                mark_curriculum_materials_seen()
                st.rerun()

    KEY_DATES = {
        date(2026, 9, 15): "📌 Declaration of Intent due",
        date(2027, 4, 15): "📌 Annual assessment (target window)",
    }

    def render_day_blocks(d, allow_marking, key_prefix, show_progress=True):
        """Renders one day's schedule blocks. Returns (done, total) so callers
        can roll these into a bigger checklist instead of showing the
        per-block bar — Today does that, Calendar keeps its own."""
        school_year = student_row["school_year"] or "current"
        holiday_label = get_holiday_for_date(school_year, d)
        if holiday_label:
            st.success(f"🎉 No school today — {holiday_label}")
            return 0, 0
        day_name = d.strftime("%A")
        blocks = WEEKLY_SCHEDULE.get(day_name)
        if not blocks:
            st.info("No school scheduled on this day. 🎉")
            return 0, 0
        chosen_electives = get_student_electives(student_id, school_year)
        elective_pool = get_elective_pool_dict()
        books = get_student_books(student_id, school_year)
        current_book = None
        if not books.empty:
            reading = books[books["status"] == "reading"]
            if not reading.empty:
                current_book = reading.iloc[0]

        done_ct = 0
        for block in blocks:
            subject, start, end = block[0], block[1], block[2]
            resource_key = block[3] if len(block) > 3 else subject
            entry = get_block_entry(student_id, d, subject, start)
            status = entry["status"] if entry is not None else None
            if status:
                done_ct += 1
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    badge = {"pending": "🕓 Waiting for parent approval",
                             "approved": "✅ Approved",
                             "rejected": "❌ Sent back — redo/ask parent"}.get(status, "")
                    if entry is not None and entry.get("struggled"):
                        badge += " · 😕 Marked as struggled"
                    chip_color = QUEST_SUBJECT_COLORS.get(subject, "#FFD23F")
                    tick = "✅" if status else "⬜"
                    st.markdown(
                        f'{tick} <span style="background:{chip_color};border:2px solid #1A1610;'
                        f'border-radius:6px;padding:2px 10px;font-weight:800;font-size:14.5px;'
                        f'display:inline-block">{QUEST_TITLES.get(subject, subject)}</span> {badge}',
                        unsafe_allow_html=True)
                    if subject == "Electives":
                        if chosen_electives.empty:
                            st.info("No electives picked yet — choose some in the "
                                    "🎯 Electives & Books tab.")
                            done_label = "elective work"
                        else:
                            for _, e in chosen_electives.iterrows():
                                info = elective_pool.get(e["elective_name"])
                                if info:
                                    st.markdown(f"🔗 **{e['elective_name']}** — "
                                                f"[{info[0]}]({info[1]})")
                                    st.caption(info[2])
                            done_label = ", ".join(chosen_electives["elective_name"])
                    else:
                        res = CURRICULUM_RESOURCES.get(resource_key,
                            CURRICULUM_RESOURCES.get(subject, CURRICULUM_RESOURCES["Electives"]))
                        st.markdown(f"🔗 [{res[0]}]({res[1]})")
                        st.caption(res[2])
                        done_label = res[0]
                        if subject == "Reading" and current_book is not None:
                            st.markdown(f"📖 Currently reading: **{current_book['title']}** "
                                        f"by {current_book['author']}")
                        steps = res[3] if len(res) > 3 else []
                        if steps:
                            with st.expander("📋 Step-by-step — exactly what to do"):
                                for i, step in enumerate(steps, start=1):
                                    st.markdown(f"{i}. {step}")
                with c2:
                    if status is None and allow_marking:
                        if st.button("✅ Done, got it",
                                     key=f"{key_prefix}_{d.isoformat()}_{subject}_{start}"):
                            add_entry(student_id, d, subject, block_hours(start, end),
                                      f"Completed via {done_label}", "Instruction", "pending",
                                      struggled=False, block_start=start)
                            st.rerun()
                        if st.button("😕 Done, still fuzzy",
                                     key=f"{key_prefix}_fuzzy_{d.isoformat()}_{subject}_{start}"):
                            add_entry(student_id, d, subject, block_hours(start, end),
                                      f"Completed via {done_label}", "Instruction", "pending",
                                      struggled=True, block_start=start)
                            st.rerun()
        if show_progress:
            st.progress(done_ct / len(blocks),
                        text=f"{done_ct} / {len(blocks)} blocks logged")
        return done_ct, len(blocks)

    def _day_context(d):
        """Shared setup for the board views: the day's blocks plus the bits
        each card needs to describe itself. Returns None on a no-school day
        (the caller has already been told why)."""
        school_year = student_row["school_year"] or "current"
        holiday_label = get_holiday_for_date(school_year, d)
        if holiday_label:
            st.success(f"🎉 No school today — {holiday_label}")
            return None
        blocks = WEEKLY_SCHEDULE.get(d.strftime("%A"))
        if not blocks:
            st.info("No school scheduled on this day. 🎉")
            return None
        books = get_student_books(student_id, school_year)
        current_book = None
        if not books.empty:
            reading = books[books["status"] == "reading"]
            if not reading.empty:
                current_book = reading.iloc[0]
        items = []
        for block in blocks:
            subject, start, end = block[0], block[1], block[2]
            entry = get_block_entry(student_id, d, subject, start)
            items.append({
                "subject": subject, "start": start, "end": end,
                "resource_key": block[3] if len(block) > 3 else subject,
                "entry": entry,
                "status": entry["status"] if entry is not None else None,
                "struggled": bool(entry.get("struggled")) if entry is not None else False,
            })
        return {"items": items, "school_year": school_year,
                "current_book": current_book,
                "electives": get_student_electives(student_id, school_year),
                "elective_pool": get_elective_pool_dict()}

    def render_today_board(d, key_prefix):
        """Today as a two-lane sprint board: cards start in To Do and move to
        Done as he logs them. Returns (done, total).

        A flat list gave a 13-year-old no sense of progress — the whole point
        here is watching work physically move across the board.
        """
        ctx = _day_context(d)
        if ctx is None:
            return 0, 0
        items = ctx["items"]
        todo = [i for i in items if i["status"] is None]
        done = [i for i in items if i["status"] is not None]

        lane_todo, lane_done = st.columns(2)
        with lane_todo:
            st.markdown(f'<div class="slane-head">🎯 To do ({len(todo)})</div>',
                        unsafe_allow_html=True)
            if not todo:
                st.markdown("**Board's clear.** Nothing left. 🎉")
            for it in todo:
                subject, start, end = it["subject"], it["start"], it["end"]
                render_block_card(subject, start, end, it["status"], it["struggled"])
                if subject == "Electives":
                    if ctx["electives"].empty:
                        st.caption("No electives picked yet — grab some in "
                                   "🎯 Electives & Books.")
                        done_label = "elective work"
                    else:
                        for _, e in ctx["electives"].iterrows():
                            info = ctx["elective_pool"].get(e["elective_name"])
                            if info:
                                st.markdown(f"🔗 [{e['elective_name']}]({info[1]})")
                        done_label = ", ".join(ctx["electives"]["elective_name"])
                else:
                    res = CURRICULUM_RESOURCES.get(
                        it["resource_key"],
                        CURRICULUM_RESOURCES.get(subject,
                                                 CURRICULUM_RESOURCES["Electives"]))
                    st.markdown(f"🔗 [{res[0]}]({res[1]})")
                    done_label = res[0]
                    if subject == "Reading" and ctx["current_book"] is not None:
                        st.caption(f"📖 {ctx['current_book']['title']}")
                    steps = res[3] if len(res) > 3 else []
                    if steps:
                        with st.expander("📋 What to do"):
                            for i, step in enumerate(steps, start=1):
                                st.markdown(f"{i}. {step}")
                b1, b2 = st.columns(2)
                if b1.button("✅ Got it", use_container_width=True,
                             key=f"{key_prefix}_{d.isoformat()}_{subject}_{start}"):
                    add_entry(student_id, d, subject, block_hours(start, end),
                              f"Completed via {done_label}", "Instruction",
                              "pending", struggled=False, block_start=start)
                    st.rerun()
                if b2.button("😕 Fuzzy", use_container_width=True,
                             key=f"{key_prefix}_fuzzy_{d.isoformat()}_{subject}_{start}"):
                    add_entry(student_id, d, subject, block_hours(start, end),
                              f"Completed via {done_label}", "Instruction",
                              "pending", struggled=True, block_start=start)
                    st.rerun()
                st.markdown("")
        with lane_done:
            st.markdown(f'<div class="slane-head done">✅ Done ({len(done)})</div>',
                        unsafe_allow_html=True)
            if not done:
                st.caption("Nothing here yet. Move a card over. 👉")
            for it in done:
                render_block_card(it["subject"], it["start"], it["end"],
                                  it["status"], it["struggled"])
        return len(done), len(items)

    def render_week_board(d):
        """The week as a five-lane board, one lane per school day, so he can
        see the whole sprint at once and today in context. Read-only —
        marking work off happens on Today."""
        school_year = student_row["school_year"] or "current"
        monday = d - timedelta(days=d.weekday())
        days = [monday + timedelta(days=i) for i in range(5)]
        lanes = st.columns(5)
        for lane, day in zip(lanes, days):
            with lane:
                is_today = day == d
                st.markdown(
                    f'<div class="slane-head{" today" if is_today else ""}">'
                    f'{day.strftime("%a")} {day.day}{" 👈" if is_today else ""}</div>',
                    unsafe_allow_html=True)
                holiday = get_holiday_for_date(school_year, day)
                if holiday:
                    st.caption(f"🎉 {holiday}")
                    continue
                blocks = WEEKLY_SCHEDULE.get(day.strftime("%A")) or []
                if not blocks:
                    st.caption("—")
                    continue
                for block in blocks:
                    subject, start, end = block[0], block[1], block[2]
                    entry = get_block_entry(student_id, day, subject, start)
                    status = entry["status"] if entry is not None else None
                    render_block_card(subject, start, end, status,
                                      bool(entry.get("struggled")) if entry is not None
                                      else False)

    if st.session_state.student_view == "Day 1 Checklist":
        school_year = student_row["school_year"] or "current"
        render_day1_checklist(student_id, school_year)

    elif st.session_state.student_view == "Today":
        d = date.today()
        st.subheader(f"{d.strftime('%A')}, {d.strftime('%B %d')}")
        today_school_year = student_row["school_year"] or "current"

        # The checklist header sits at the top but can't be drawn until the
        # blocks and check-in below report how many are done — so reserve the
        # slot now and fill it at the end of the run.
        checklist_slot = st.container()

        active_quest = get_active_fun_project(student_id, today_school_year)
        if active_quest is not None:
            with st.container(border=True):
                st.markdown(f"### {active_quest['icon'] or '🗺️'} "
                           f"Current Quest: {active_quest['title']}")
                st.caption(active_quest["description"])
                steps = parse_steps(active_quest["steps"])
                if steps:
                    with st.expander("📋 Quest steps"):
                        for i, s in enumerate(steps, 1):
                            st.markdown(f"{i}. {s}")
                if st.button("🏁 Mark quest finished", key="today_finish_quest"):
                    finish_fun_project(
                        int(active_quest["id"]), student_id, active_quest["title"],
                        active_quest["subjects"] or active_quest["subject"],
                        active_quest["est_hours"] or 1.0)
                    st.success("Quest complete! Sent to your parent for approval.")
                    st.rerun()

        trivia = get_daily_trivia(d)
        with st.container(border=True):
            st.markdown(f"🎲 **Did you know?** _{trivia['subject']}_")
            st.caption(trivia["fact"])

        if d in KEY_DATES:
            st.warning(KEY_DATES[d])
        st.markdown(QUEST_CARD_CSS, unsafe_allow_html=True)
        blocks_done, blocks_total = render_today_board(d, key_prefix="today")

        qsubj, qtopic = suggest_quiz_for_day(student_id, d)
        if qsubj:
            with st.container(border=True):
                st.markdown(f"📝 **Suggested quiz today:** {qsubj} — {qtopic}")
                if st.button("Take this quiz", key="today_take_quiz"):
                    st.session_state["quiz_subject"] = qsubj
                    st.session_state["quiz_topic"] = qtopic
                    st.success("Selected — head to the 📝 Quizzes tab.")

        finished_this_month = count_finished_fun_projects_in_month(
            student_id, today_school_year, d.year, d.month)
        days_left_in_month = cal.monthrange(d.year, d.month)[1] - d.day
        if finished_this_month == 0 and days_left_in_month <= 7:
            st.info(f"🌟 No quest finished yet this month — "
                    f"{days_left_in_month} day(s) left. Check out the "
                    "🗺️ Passion Track tab!")

        checkin_done = render_health_habits_checkin(student_id)

        # --- fill in the checklist header reserved at the top of the view
        todo_done = blocks_done + int(checkin_done)
        todo_total = blocks_total + 1  # the blocks, plus the health check-in
        with checklist_slot:
            if blocks_total == 0:
                # holiday/weekend — render_day_blocks already said so
                pass
            else:
                left = todo_total - todo_done
                if todo_done == 0:
                    hype = "Let's get after it 💪"
                elif left == 0:
                    hype = "Everything's done — go enjoy your day! 🎉"
                elif left == 1:
                    hype = "One left. So close! 🔥"
                elif todo_done >= todo_total / 2:
                    hype = "Over halfway — keep rolling 🚀"
                else:
                    hype = "Nice start — keep going ⭐"
                st.markdown(f"### ✅ Today's checklist — {todo_done}/{todo_total}")
                st.progress(todo_done / todo_total, text=hype)
                if left == 0:
                    st.success("🏆 Full sweep! Every block logged and your "
                               "check-in is in. That's a complete day.")
                    # only pop the confetti the first time it hits 100% today
                    party_key = f"party_{d.isoformat()}"
                    if not st.session_state.get(party_key):
                        st.session_state[party_key] = True
                        st.balloons()
                st.caption("Your to-dos: each subject block below, plus your "
                           "health check-in at the bottom.")
                st.divider()

    elif st.session_state.student_view == "Calendar":
        if "cal_month" not in st.session_state:
            st.session_state.cal_month = date.today().replace(day=1)

        nav1, nav2, nav3 = st.columns([1, 3, 1])
        with nav1:
            if st.button("◀ Prev"):
                m = st.session_state.cal_month
                st.session_state.cal_month = (m.replace(day=1) - timedelta(days=1)).replace(day=1)
                st.rerun()
        with nav3:
            if st.button("Next ▶"):
                m = st.session_state.cal_month
                st.session_state.cal_month = (m.replace(day=28) + timedelta(days=7)).replace(day=1)
                st.rerun()
        month = st.session_state.cal_month
        with nav2:
            st.markdown(f"<h3 style='text-align:center;margin:0'>"
                        f"{month.strftime('%B %Y')}</h3>", unsafe_allow_html=True)

        # status lookup: date iso -> list of statuses logged that day
        all_entries = get_entries(student_id)
        by_date = {}
        if not all_entries.empty:
            for _, r in all_entries.iterrows():
                by_date.setdefault(r["entry_date"], []).append(r["status"])
        quiz_dates = get_quiz_dates(student_id)
        cal_school_year = student_row["school_year"] or "current"
        fun_dates = get_finished_fun_project_dates(student_id, cal_school_year)
        holidays_df = get_holidays_df(cal_school_year)

        def holiday_label_for(d):
            if holidays_df.empty:
                return None
            iso = d.isoformat()
            match = holidays_df[(holidays_df["start_date"] <= iso)
                               & (holidays_df["end_date"] >= iso)]
            return match.iloc[0]["label"] if not match.empty else None

        def day_marker(d):
            if holiday_label_for(d):
                return "🎉"
            blocks = WEEKLY_SCHEDULE.get(d.strftime("%A"))
            logged = by_date.get(d.isoformat(), [])
            if not blocks:
                return "✅" if logged else ""
            if logged:
                if any(s == "pending" for s in logged):
                    return "🕓"
                if len(logged) >= len(blocks):
                    return "✅"
                return "🟡"
            return "⬜" if d >= date.today() else "▫️"

        today = date.today()
        weeks = cal.Calendar(firstweekday=6).monthdatescalendar(month.year, month.month)
        html = ("<table style='width:100%;border-collapse:collapse;text-align:center'>"
                "<tr>" + "".join(
                    f"<th style='padding:6px;border:1px solid #ddd;background:#f2f2f2'>{w}</th>"
                    for w in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]) + "</tr>")
        for week in weeks:
            html += "<tr>"
            for d in week:
                in_month = d.month == month.month
                is_today = d == today
                is_holiday = in_month and holiday_label_for(d)
                if is_today:
                    bg = "#fff8e1"
                elif is_holiday:
                    bg = "#e6f7e9"
                elif in_month:
                    bg = "#fff"
                else:
                    bg = "#fafafa"
                color = "#222" if in_month else "#bbb"
                border = "2px solid #f0a500" if is_today else "1px solid #ddd"
                pin = " 📌" if d in KEY_DATES and in_month else ""
                marker = day_marker(d) if in_month else ""
                quiz_mark = " 📝" if in_month and d.isoformat() in quiz_dates else ""
                fun_mark = " 🌟" if in_month and d.isoformat() in fun_dates else ""
                html += (f"<td style='padding:8px 4px;border:{border};background:{bg};"
                         f"color:{color};vertical-align:top;height:52px'>"
                         f"<div style='font-weight:600'>{d.day}{pin}</div>"
                         f"<div style='font-size:1.05em'>{marker}{quiz_mark}{fun_mark}"
                         "</div></td>")
            html += "</tr>"
        html += "</table>"
        st.markdown(html, unsafe_allow_html=True)
        st.caption("✅ all blocks done · 🟡 partly done · 🕓 waiting for approval · "
                   "⬜ school day coming up · ▫️ past day not logged · 📌 key date · "
                   "📝 quiz taken · 🎉 holiday/break · 🌟 quest finished")

        month_fun_ct = count_finished_fun_projects_in_month(
            student_id, cal_school_year, month.year, month.month)
        if month_fun_ct > 0:
            st.caption(f"🌟 {month_fun_ct} quest(s) finished this month.")
        elif month.year == today.year and month.month == today.month:
            st.caption("🌟 No quest finished yet this month — check the "
                      "🗺️ Passion Track tab.")

        if not holidays_df.empty:
            month_holidays = holidays_df[
                holidays_df["start_date"].apply(
                    lambda s: date.fromisoformat(s).year == month.year
                    and date.fromisoformat(s).month == month.month)
                | holidays_df["end_date"].apply(
                    lambda s: date.fromisoformat(s).year == month.year
                    and date.fromisoformat(s).month == month.month)]
            if not month_holidays.empty:
                st.markdown("**Holidays/breaks this month:**")
                for _, h in month_holidays.iterrows():
                    st.markdown(f"- {h['label']}: {fmt_date(h['start_date'])} to "
                               f"{fmt_date(h['end_date'])}")

        month_keys = {d: label for d, label in KEY_DATES.items()
                      if d.year == month.year and d.month == month.month}
        if month_keys:
            st.markdown("**Key dates this month:**")
            for d, label in sorted(month_keys.items()):
                st.markdown(f"- {d.strftime('%b %d')}: {label}")

        st.divider()
        st.subheader("Open a day")
        pick = st.date_input("Pick any date", value=today, format="MM-DD-YYYY",
                             key="cal_pick")
        if pick in KEY_DATES:
            st.warning(KEY_DATES[pick])
        allow = pick <= today  # can log today and catch up past days, not future
        if not allow:
            st.caption("Future day — you can see the plan but can't mark it done yet.")
        render_day_blocks(pick, allow_marking=allow, key_prefix="cal")

    elif st.session_state.student_view == "My Week":
        _d = date.today()
        _monday = _d - timedelta(days=_d.weekday())
        st.subheader(f"🗓️ This week's board "
                     f"({_monday.strftime('%b %d')} – "
                     f"{(_monday + timedelta(days=4)).strftime('%b %d')})")
        st.markdown(QUEST_CARD_CSS, unsafe_allow_html=True)
        _wk_done = sum(
            1 for i in range(5)
            for b in (WEEKLY_SCHEDULE.get((_monday + timedelta(days=i)).strftime("%A")) or [])
            if get_block_entry(student_id, _monday + timedelta(days=i), b[0], b[1]) is not None)
        _wk_total = sum(
            len(WEEKLY_SCHEDULE.get((_monday + timedelta(days=i)).strftime("%A")) or [])
            for i in range(5))
        if _wk_total:
            st.progress(_wk_done / _wk_total,
                        text=f"{_wk_done} / {_wk_total} cards cleared this week")
        st.caption("Faded, struck-through cards are ones you've already logged. "
                   "Mark work off over on 📅 Today.")
        render_week_board(_d)

    elif st.session_state.student_view == "8th Grade Scope":
        render_scope_reference()

    elif st.session_state.student_view == "Passion Track":
        school_year = student_row["school_year"] or "current"
        render_fun_projects_picker(student_id, school_year, key_prefix="stu")

    elif st.session_state.student_view == "My Plan":
        school_year = student_row["school_year"] or "current"
        render_this_week(student_id, school_year, key_prefix="stu")

    elif st.session_state.student_view == "Foundations":
        school_year = student_row["school_year"] or "current"
        render_foundations(student_id, school_year, key_prefix="stu")

    elif st.session_state.student_view == "Travel Log":
        school_year = student_row["school_year"] or "current"
        render_travel_log(student_id, school_year, key_prefix="stu")

    elif st.session_state.student_view == "Electives & Books":
        school_year = student_row["school_year"] or "current"
        render_student_curriculum_setup(student_id, school_year)

    elif st.session_state.student_view == "Quizzes":
        st.subheader("Quizzes")
        st.caption("Pick a subject and topic to test what you've learned. "
                   "Auto-graded and saved straight to your Grades.")
        qsubj = st.selectbox("Subject", list(QUIZ_BANK.keys()), key="quiz_subject")
        qtopic = st.selectbox("Topic", list(QUIZ_BANK[qsubj].keys()), key="quiz_topic")
        quiz_key = f"{qsubj}::{qtopic}"
        questions = QUIZ_BANK[qsubj][qtopic]

        if "quiz_results" not in st.session_state:
            st.session_state.quiz_results = {}
        if "quiz_start_times" not in st.session_state:
            st.session_state.quiz_start_times = {}
        result = st.session_state.quiz_results.get(quiz_key)

        if result is None:
            if quiz_key not in st.session_state.quiz_start_times:
                st.session_state.quiz_start_times[quiz_key] = time.time()

            st.info("⏱️ We track how long quizzes take — take your time to "
                    "read each question and think it through.")
            with st.form(key=f"quiz_form_{quiz_key}"):
                responses = []
                for i, q in enumerate(questions):
                    ans = st.radio(f"**{i + 1}. {q['q']}**", q["choices"],
                                   index=None, key=f"quiz_a_{quiz_key}_{i}")
                    responses.append(ans)
                if st.form_submit_button("Submit quiz", type="primary"):
                    correct = sum(1 for q, a in zip(questions, responses)
                                 if a == q["answer"])
                    total = len(questions)
                    missed = [str(i + 1) for i, (q, a) in enumerate(zip(questions, responses))
                             if a != q["answer"]]

                    elapsed = time.time() - st.session_state.quiz_start_times[quiz_key]
                    floor = QUIZ_SEC_PER_QUESTION * total
                    rushed = elapsed < floor

                    notes = (f"{correct}/{total} correct." if not missed else
                            f"{correct}/{total} correct. Missed Q{', Q'.join(missed)}.")
                    notes += f" Completed in {format_elapsed(elapsed)}."
                    if rushed:
                        notes += f" ⚡ Flagged — faster than the {floor}s floor."
                    add_assignment(student_id, date.today(), qsubj,
                                   f"Quiz: {qtopic}", correct, total, notes)
                    st.session_state.quiz_results[quiz_key] = {
                        "correct": correct, "total": total,
                        "questions": questions, "responses": responses,
                        "elapsed": elapsed, "rushed": rushed}
                    del st.session_state.quiz_start_times[quiz_key]
                    st.rerun()
        else:
            pct = 100 * result["correct"] / result["total"]
            st.success(f"Scored {result['correct']}/{result['total']} ({pct:.0f}%, "
                       f"{letter_grade(pct)}) — saved to your Grades.")
            st.caption(f"Completed in {format_elapsed(result['elapsed'])}.")
            if result["rushed"]:
                st.warning("⚡ This one was answered faster than expected for "
                           f"{result['total']} questions — flagged for your "
                           "parent to see in Grading. Slow down and actually "
                           "read next time!")
            for i, (q, a) in enumerate(zip(result["questions"], result["responses"])):
                right = a == q["answer"]
                st.markdown(f"{'✅' if right else '❌'} **{i + 1}. {q['q']}**")
                st.caption(f"Your answer: {a or '(blank)'}"
                          + ("" if right else f" · Correct answer: {q['answer']}"))
            if st.button("Retake this quiz"):
                del st.session_state.quiz_results[quiz_key]
                st.rerun()

    elif st.session_state.student_view == "My Logins":
        render_accounts_table(student_id)

    elif st.session_state.student_view == "My Grades":
        st.subheader("My grades")
        gs = grade_summary(student_id)
        if gs.empty:
            st.info("No graded work yet.")
        else:
            st.dataframe(gs, use_container_width=True, hide_index=True)

    elif st.session_state.student_view == "Resources":
        render_resources_tab(parent_mode=False)

# ============================================================ PARENT MODE
else:
    if student_id is None:
        st.warning("Add a student in the sidebar to begin.")
        st.stop()

    title_col, link_col = st.columns([5, 1.4])
    with title_col:
        st.title(f"Parent Console — {student_row['name']} "
                 f"({student_row['school_year'] or 'current year'})")
    with link_col:
        st.link_button("🎒 Open Student View", "?view=student", use_container_width=True)

    reminder = get_assessment_reminder(student_id, student_row["school_year"] or "current")
    if reminder:
        level, msg = reminder
        {"error": st.error, "warning": st.warning, "info": st.info}[level](msg)

    doi_school_year = student_row["school_year"] or "current"
    doi = get_doi_reminder(doi_school_year)
    if doi:
        doi_level, doi_days_left, doi_deadline = doi
        doi_msg = (f"⚠️ **Declaration of Intent overdue** — the {fmt_date(doi_deadline)} "
                   "deadline has passed." if doi_days_left <= 0 else
                   f"📌 **Declaration of Intent due in {doi_days_left} day"
                   f"{'s' if doi_days_left != 1 else ''}** — filed with your school "
                   f"district by {fmt_date(doi_deadline)} (WA RCW 28A.200.010).")
        {"error": st.error, "warning": st.warning, "info": st.info}[doi_level](doi_msg)
        with st.expander("📋 Steps & letter template"):
            st.markdown(
                "1. Check your district's site first — many post their own form.\n"
                "2. No district form? The letter below satisfies the legal requirement.\n"
                "3. Email is fine for most WA districts — confirm with yours.\n"
                "4. Keep a copy/confirmation in your records.\n"
                "5. This is filed every school year, not once.")
            st.text_area("Letter template — copy and fill in the brackets",
                         value=doi_letter_template(student_row["name"], doi_school_year),
                         height=320, key="doi_letter_text")
            if st.button("✅ Filed — dismiss this reminder", key="doi_dismiss"):
                setting_set(f"doi_dismissed_{doi_school_year}", "1")
                st.rerun()

    # Parent panes are now driven by the sidebar nav (st.session_state.
    # parent_view) instead of st.tabs — one pane renders per run, mirroring
    # the Student view. school_year is set once here so every branch has it.
    school_year = student_row["school_year"] or "current"
    parent_view = st.session_state.get("parent_view", "Review & Approve")

    # ---- Launch Checklist
    if parent_view == "Launch Checklist":
        render_launch_checklist(student_id, school_year)

    # ---- Review & Approve
    elif parent_view == "Review & Approve":
        pending = get_entries(student_id, statuses=["pending"])
        st.subheader(f"Pending entries ({len(pending)})")
        st.caption("Only APPROVED hours count toward the 1,000-hour / 180-day requirement.")
        if pending.empty:
            st.success("Nothing waiting for review.")
        for _, row in pending.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 1.2, 1, 1])
                with c1:
                    flag = " · 😕 He marked this as struggled" if row.get("struggled") else ""
                    st.markdown(f"**{fmt_date(row['entry_date'])} · {row['subject']}**{flag}")
                    st.caption(row["description"] or "")
                with c2:
                    adj = st.number_input("Hours", value=float(row["hours"]),
                                          min_value=0.0, max_value=12.0, step=0.25,
                                          key=f"adj_{row['id']}")
                with c3:
                    if st.button("Approve", key=f"ap_{row['id']}", type="primary"):
                        update_entry_status(int(row["id"]), "approved", adj)
                        st.rerun()
                with c4:
                    if st.button("Reject", key=f"rj_{row['id']}"):
                        update_entry_status(int(row["id"]), "rejected")
                        st.rerun()

    # ---- Manual Log (auto-approved)
    elif parent_view == "Manual Log":
        st.subheader("Add an entry (auto-approved)")
        st.caption("Field trips, co-op days, catch-up work, anything outside the standard blocks.")
        c1, c2, c3 = st.columns(3)
        with c1:
            e_date = st.date_input("Date", value=date.today(), format="MM-DD-YYYY",
                                   key="ml_date")
            day_type = st.selectbox("Day type",
                ["Instruction", "Field Trip", "Sick", "Holiday", "Co-op/Class"])
        with c2:
            subj = st.selectbox("Subject", WA_SUBJECTS + ["Electives"])
            hrs = st.number_input("Hours", 0.0, 12.0, 1.0, 0.25)
        with c3:
            desc = st.text_area("Description", height=100)
        if st.button("Add entry", type="primary"):
            add_entry(student_id, e_date, subj, hrs, desc, day_type, "approved")
            st.success("Logged.")
            st.rerun()

        st.divider()
        st.subheader("All entries")
        all_df = get_entries(student_id)
        if not all_df.empty:
            show = all_df[["id", "entry_date", "subject", "hours", "day_type",
                           "status", "description"]].copy()
            show["entry_date"] = show["entry_date"].apply(fmt_date)
            show = show.rename(columns={
                "id": "ID", "entry_date": "Date", "subject": "Subject",
                "hours": "Hours", "day_type": "Type", "status": "Status",
                "description": "Notes"})
            st.dataframe(show, use_container_width=True, hide_index=True)
            with st.expander("Delete an entry"):
                did = st.number_input("Entry ID", min_value=0, step=1)
                if st.button("Delete entry"):
                    delete_entry(did)
                    st.rerun()

    # ---- Grading
    elif parent_view == "Grading":
        st.subheader("Record a grade")
        c1, c2, c3 = st.columns(3)
        with c1:
            g_date = st.date_input("Date", value=date.today(), format="MM-DD-YYYY",
                                   key="g_date")
            g_subj = st.selectbox("Subject", WA_SUBJECTS + ["Electives"], key="g_subj")
        with c2:
            g_title = st.text_input("Assignment / quiz / test name")
            g_score = st.number_input("Score", 0.0, 1000.0, 90.0, 0.5)
        with c3:
            g_max = st.number_input("Out of", 1.0, 1000.0, 100.0, 0.5)
            g_notes = st.text_input("Notes (optional)")
        g_photo = st.file_uploader(
            "Photo of the work (optional — for handwritten/non-digital work)",
            type=["png", "jpg", "jpeg", "heic"], key="g_photo")
        if st.button("Save grade", type="primary"):
            if g_title.strip():
                g_photo_path = (save_uploaded_photo(g_photo, student_id, "grading")
                                if g_photo is not None else None)
                add_assignment(student_id, g_date, g_subj, g_title.strip(),
                               g_score, g_max, g_notes, g_photo_path)
                st.success(f"Saved — {100*g_score/g_max:.1f}% "
                           f"({letter_grade(100*g_score/g_max)})")
                st.rerun()
            else:
                st.warning("Give the assignment a name.")

        with st.expander("📄 Free printable worksheets (non-digital work)"):
            st.caption("For handwritten practice — print, have him complete it on "
                       "paper, then log the grade above with a photo of the work.")
            st.markdown(
                "- [Math-Drills.com](https://www.math-drills.com) — printable math "
                "worksheets, all topics\n"
                "- [CommonCoreSheets.com](https://www.commoncoresheets.com) — "
                "free worksheets across subjects, by grade level\n"
                "- [HomeschoolMath.net](https://www.homeschoolmath.net/worksheets/) "
                "— free math worksheet generator\n"
                "- [EnglishLinx.com](https://www.englishlinx.com/8th_grade/) — "
                "8th-grade reading/writing/grammar worksheets\n"
                "- [K12Reader.com](https://www.k12reader.com) — reading "
                "comprehension & language arts worksheets\n"
                "- [ReadWorks.org](https://www.readworks.org) — printable PDF "
                "reading passages (already used for Language Arts)")

        st.divider()
        st.subheader("Grade summary")
        gs = grade_summary(student_id)
        if gs.empty:
            st.info("No graded work yet.")
        else:
            st.dataframe(gs, use_container_width=True, hide_index=True)

        st.subheader("All graded work")
        ga = get_assignments(student_id)
        if not ga.empty:
            ga_show = ga.copy()
            ga_show["%"] = (100 * ga_show["score"] / ga_show["max_score"]).round(1)
            ga_show["Letter"] = ga_show["%"].apply(letter_grade)
            ga_show["📷"] = ga_show["photo_path"].apply(lambda p: "📷" if p else "")
            ga_show["assign_date"] = ga_show["assign_date"].apply(fmt_date)
            st.dataframe(ga_show[["id", "assign_date", "subject", "title",
                                  "score", "max_score", "%", "Letter", "notes", "📷"]].rename(
                columns={"id": "ID", "assign_date": "Date", "subject": "Subject",
                         "title": "Assignment", "score": "Score",
                         "max_score": "Out of", "notes": "Notes"}),
                use_container_width=True, hide_index=True)
            with_photos = ga[ga["photo_path"].notna() & (ga["photo_path"] != "")]
            if not with_photos.empty:
                with st.expander(f"📷 Photos of graded work ({len(with_photos)})"):
                    for _, r in with_photos.iterrows():
                        photo_full_path = Path(__file__).parent / r["photo_path"]
                        if photo_full_path.exists():
                            st.caption(f"{fmt_date(r['assign_date'])} — {r['title']}")
                            st.image(str(photo_full_path), width=300)
            with st.expander("Delete a grade"):
                gid = st.number_input("Grade ID", min_value=0, step=1, key="del_grade")
                if st.button("Delete grade"):
                    delete_assignment(gid)
                    st.rerun()

    # ---- Dashboard (approved hours only)
    elif parent_view == "Dashboard":
        approved = get_entries(student_id, statuses=["approved"])
        st.subheader("Compliance progress (approved hours only)")
        if approved.empty:
            st.info("No approved entries yet.")
        else:
            total_hours = approved["hours"].sum()
            days = approved[approved["day_type"] == "Instruction"]["entry_date"].nunique()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Hours", f"{total_hours:.1f}", f"of {REQUIRED_HOURS}")
            c2.metric("Days", days, f"of {REQUIRED_DAYS}")
            c3.metric("Hours left", f"{max(0, REQUIRED_HOURS - total_hours):.0f}")
            c4.metric("Days left", max(0, REQUIRED_DAYS - days))
            st.progress(min(1.0, total_hours / REQUIRED_HOURS), text="Hours")
            st.progress(min(1.0, days / REQUIRED_DAYS), text="Days")

            st.divider()
            # planned vs actual this week
            monday = date.today() - timedelta(days=date.today().weekday())
            friday = monday + timedelta(days=4)
            st.subheader(f"This week vs plan ({monday.strftime('%b %d')}–{friday.strftime('%b %d')})")
            approved["d"] = pd.to_datetime(approved["entry_date"]).dt.date
            wk = approved[(approved["d"] >= monday) & (approved["d"] <= friday)]
            actual = wk.groupby("subject")["hours"].sum()
            rows = []
            for s, p in planned_hours_by_subject().items():
                a = float(actual.get(s, 0.0))
                stat = "✅" if a >= p else ("⬜" if a == 0 else "🟡")
                rows.append({"Subject": s, "Planned": p, "Actual": round(a, 2), "": stat})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption("Planned is calculated from the weekly schedule, so a "
                       "week with every block done reads as 100%.")

            st.subheader("Hours by subject (year)")
            st.bar_chart(approved.groupby("subject")["hours"].sum().sort_values(ascending=False))

        st.divider()
        render_health_habits_summary(student_id)

        st.divider()
        render_support_resources(student_id)

    # ---- Curriculum
    elif parent_view == "Curriculum":
        st.subheader("WA's 11 required subject areas")
        approved = get_entries(student_id, statuses=["approved"])
        for s in WA_SUBJECTS:
            h = approved[approved["subject"] == s]["hours"].sum() if not approved.empty else 0
            st.write(f"{'✅' if h > 0 else '⬜'} **{s}** — {h:.1f} hrs")
        st.caption("No per-subject minimum in WA law — this just flags neglect early.")

        st.divider()
        school_year = student_row["school_year"] or "current"
        render_electives_books(student_id, school_year, key_prefix="parent",
                               is_parent=True)

        st.divider()
        render_elective_pool_admin(school_year)

        st.divider()
        render_book_pool_admin()

        st.divider()
        render_proposals_review(student_id, school_year)

    # ---- 8th Grade Scope
    elif parent_view == "8th Grade Scope":
        render_scope_reference()

    # ---- Quest Board
    elif parent_view == "Passion Track":
        school_year = student_row["school_year"] or "current"
        render_fun_projects_picker(student_id, school_year, key_prefix="parent")
        st.divider()
        render_fun_project_pool_admin()

    # ---- Plan Blender
    elif parent_view == "Plan Blender":
        school_year = student_row["school_year"] or "current"
        render_plan_blender(student_id, school_year)

    # ---- Foundations
    elif parent_view == "Foundations":
        school_year = student_row["school_year"] or "current"
        render_foundations(student_id, school_year, key_prefix="parentfnd")
        st.divider()
        render_foundations_admin()

    # ---- Travel Log
    elif parent_view == "Travel Log":
        school_year = student_row["school_year"] or "current"
        render_travel_log(student_id, school_year, key_prefix="parent")
        st.divider()
        render_national_park_pool_admin()
        st.divider()
        render_major_city_pool_admin()

    # ---- Accounts
    elif parent_view == "Accounts":
        school_year = student_row["school_year"] or "current"
        render_accounts_checklist(student_id, school_year)

    # ---- Assessments
    elif parent_view == "Assessments":
        st.subheader("Annual assessment record")
        with st.expander("📜 What WA law actually requires", expanded=False):
            st.markdown(WA_ASSESSMENT_LAW)
        with st.expander("🔗 Where to actually get this done", expanded=False):
            st.markdown(WA_ASSESSMENT_RESOURCES)
        with st.expander("🧭 How our curriculum lines up with these tests",
                         expanded=False):
            st.markdown(
                "Standardized tests like ITBS/Stanford/CAT score these as "
                "separate sections. Where we were thin, we added Quiz "
                "topics (🎒 Student > 📝 Quizzes) in the matching skill area:\n\n"
                "- **Reading Comprehension** — ✅ covered (CommonLit)\n"
                "- **Vocabulary** — added: Reading > *Vocabulary in Context*\n"
                "- **Spelling / Capitalization / Punctuation** — added: "
                "Writing > *Grammar & Mechanics*\n"
                "- **Math Concepts & Problem Solving** — ✅ covered (Khan Academy)\n"
                "- **Math Computation** — added: Mathematics > "
                "*Math Computation Practice*\n"
                "- **Science** — ✅ covered (CK-12)\n"
                "- **Social Studies** — ✅ covered (Khan Academy Civics/Economics)\n"
                "- **Maps, Diagrams & Reference Skills** — added: Social "
                "Studies > *Maps, Diagrams & Reference Skills*\n\n"
                "These practice the same skill categories and multiple-choice "
                "format as the real test, not the actual test questions "
                "(those are copyrighted) — the goal is familiarity, not a "
                "guaranteed score.")
        c1, c2 = st.columns(2)
        with c1:
            a_date = st.date_input("Date", value=date.today(), format="MM-DD-YYYY",
                                   key="as_date")
            a_type = st.selectbox("Type", ["Standardized Test",
                                           "Certificated Person Evaluation", "Other"])
        with c2:
            evaluator = st.text_input("Evaluator / test name")
            result = st.text_input("Result summary")
        a_notes = st.text_area("Notes", key="as_notes")
        if st.button("Save assessment", type="primary"):
            add_assessment(student_id, a_date, a_type, evaluator, result, a_notes)
            st.rerun()
        hist = get_assessments(student_id)
        if not hist.empty:
            hist_show = hist.copy()
            hist_show["assessment_date"] = hist_show["assessment_date"].apply(fmt_date)
            st.dataframe(hist_show[["assessment_date", "assessment_type", "evaluator",
                                    "result", "notes"]], use_container_width=True,
                         hide_index=True)

    # ---- Export
    elif parent_view == "Export":
        st.subheader("Records & ESA Packet")
        school_year = student_row["school_year"] or "current"
        base = student_row["name"].replace(" ", "_")

        st.markdown("**📄 ESA / compliance packet**")
        st.caption("One printable page: hours by subject, completed Foundations "
                   "modules *with what was learned* (the educational purpose an "
                   "ESA wants), passion projects, grades, and assessment. Open "
                   "it and use your browser's Print → Save as PDF.")
        packet_html = build_esa_packet_html(student_id, student_row, school_year)
        st.download_button("⬇️ Download records packet (HTML → print to PDF)",
            packet_html.encode(), file_name=f"{base}_records_{school_year}.html",
            mime="text/html", type="primary")
        with st.expander("👁️ Preview the packet"):
            components.html(packet_html, height=560, scrolling=True)

        st.divider()
        st.markdown("**Raw data (CSV)**")
        approved = get_entries(student_id, statuses=["approved"])
        ga = get_assignments(student_id)
        hist = get_assessments(student_id)
        if not approved.empty:
            approved_csv = approved.drop(columns=["student_id"]).copy()
            approved_csv["entry_date"] = approved_csv["entry_date"].apply(fmt_date)
            st.download_button("⬇️ Approved hours log (CSV)",
                approved_csv.to_csv(index=False).encode(),
                file_name=f"{base}_hours_log.csv", mime="text/csv")
        if not ga.empty:
            ga_csv = ga.drop(columns=["student_id"]).copy()
            ga_csv["assign_date"] = ga_csv["assign_date"].apply(fmt_date)
            st.download_button("⬇️ Grades (CSV)",
                ga_csv.to_csv(index=False).encode(),
                file_name=f"{base}_grades.csv", mime="text/csv")
        if not hist.empty:
            hist_csv = hist.drop(columns=["student_id"]).copy()
            hist_csv["assessment_date"] = hist_csv["assessment_date"].apply(fmt_date)
            st.download_button("⬇️ Assessments (CSV)",
                hist_csv.to_csv(index=False).encode(),
                file_name=f"{base}_assessments.csv", mime="text/csv")
        st.caption("These become the annual compliance packet and, later, transcript source data.")

    # ---- Settings
    elif parent_view == "Settings":
        st.caption("Schedule, curriculum links, and weekly hour targets are constants "
                   "near the top of app.py — edit that file to change the plan.")

    elif parent_view == "Resources":
        render_resources_tab(parent_mode=True)
