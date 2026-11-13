"""Builds the search landing pages in docs/<lang>/ plus docs/sitemap.xml and docs/robots.txt.

Three topics people search for -- Salesforce lead scoring, AI lead scoring,
lead scoring template -- each in Armenian, Russian and English, Armenia first.
Every page is plain static HTML (search engines read it without running
JavaScript) and points to its other language versions with hreflang.

Edit the text in PAGES below, then run:

    python scripts/build_seo_pages.py

and commit what changed under docs/.
"""

import html
import json
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
SITE = "https://www.crmscoring.com"
LANGS = ["hy", "ru", "en"]
LANG_NAMES = {"hy": "Հայերեն", "ru": "Русский", "en": "English"}
OG_LOCALE = {"hy": "hy_AM", "ru": "ru_RU", "en": "en_US"}

UI = {
    "hy": {
        "cta": "Փորձել անվճար",
        "cta_note": "Անվճար պլան՝ առանց քարտի։ Pro՝ $20/ամիս։",
        "faq": "Հաճախ տրվող հարցեր",
        "home": "Գլխավոր",
        "more": "Կարդացեք նաև",
        "contact": "Հարցեր ունե՞ք՝ գրեք",
    },
    "ru": {
        "cta": "Попробовать бесплатно",
        "cta_note": "Бесплатный тариф без карты. Pro — $20/месяц.",
        "faq": "Частые вопросы",
        "home": "Главная",
        "more": "Читайте также",
        "contact": "Есть вопросы? Пишите:",
    },
    "en": {
        "cta": "Try it free",
        "cta_note": "Free plan, no card. Pro is $20/month.",
        "faq": "Frequently asked questions",
        "home": "Home",
        "more": "Read next",
        "contact": "Questions? Email",
    },
}

# Each page: title (browser tab + Google headline), description (Google
# snippet), h1, intro, sections of (heading, paragraphs and "- " bullet
# lines), optional table, and FAQ pairs.
PAGES = {
    "salesforce-lead-scoring": {
        "hy": {
            "title": "Salesforce լիդերի գնահատում (lead scoring) — CRM Scoring",
            "description": "Գնահատեք Salesforce-ի, Bitrix24-ի, amoCRM-ի և HubSpot-ի հաճախորդներին Hot / Warm / Cold սանդղակով AI բացատրությամբ։ Աշխատում է Հայաստանի ընկերությունների համար։ Անվճար սկսելու համար։",
            "h1": "Salesforce լիդերի գնահատում՝ մի քանի րոպեում",
            "intro": "CRM Scoring-ը գնահատում է ձեր CRM-ի յուրաքանչյուր հաճախորդին 0-ից 100 միավորով, բաժանում Hot / Warm / Cold խմբերի և յուրաքանչյուրի համար գրում կարճ բացատրություն։ Վաճառքի թիմը տեսնում է, թե ում զանգել առաջինը։",
            "sections": [
                ("Ինչպես է աշխատում", [
                    "- Արտահանեք հաշիվները Salesforce-ից (Reports → Export) CSV կամ Excel ֆայլով։",
                    "- Վերբեռնեք ֆայլը CRM Scoring-ում։ Անհրաժեշտ է միայն ընկերության անունը և կայքը, մնացած սյունակները (ոլորտ, աշխատակիցների թիվ, եկամուտ, երկիր) բարելավում են գնահատումը։",
                    "- Ստացեք յուրաքանչյուր հաշվի միավորը, Hot / Warm / Cold խումբը և AI բացատրությունը։",
                    "- Pro պլանում արդյունքները մեկ սեղմումով վերադարձրեք Salesforce, իսկ Slack-ում ստացեք ծանուցում, երբ լիդը դառնում է Hot։",
                ]),
                ("Չե՞ք օգտագործում Salesforce", [
                    "Հայաստանում շատ ընկերություններ աշխատում են Bitrix24-ով, amoCRM-ով, HubSpot-ով կամ պարզապես Excel-ով։ CRM Scoring-ն ընդունում է ցանկացած CSV կամ Excel արտահանում, այնպես որ գնահատումը կաշխատի նաև ձեր դեպքում։",
                ]),
                ("Ինչու է գնահատումը թափանցիկ", [
                    "Միավորը հաշվարկվում է կանոններով, որոնք կարող եք ստուգել՝ ոլորտ (25), ընկերության չափ (25), եկամուտ (15), տեխնոլոգիաներ (15), աշխարհագրություն (10), աշխատանքի ընդունման ազդանշան (10)։ 75 և ավելի միավորը Hot է, 50–74-ը՝ Warm, 50-ից ցածրը՝ Cold։ AI-ն ավելացնում է այն, ինչ կանոնները չեն տեսնում։",
                ]),
            ],
            "faq": [
                ("Արդյո՞ք ձեր տվյալները դուրս են գալիս ընկերությունից", "CRM Scoring-ը կարելի է տեղադրել ձեր սեփական սերվերում, և CRM տվյալները մնում են ձեր ենթակառուցվածքում։"),
                ("Որքա՞ն արժե", "Starter պլանն անվճար է (10 վերբեռնում, յուրաքանչյուրը 10 տող)։ Pro-ն $20/ամիս է կամ $192/տարի, Advanced-ը՝ $40/ամիս։"),
                ("Պե՞տք է արդյոք Salesforce", "Ոչ։ Բավական է CSV կամ Excel ֆայլ ցանկացած CRM-ից։ Salesforce-ի հետ կապը պետք է միայն արդյունքները ավտոմատ վերադարձնելու համար։"),
            ],
        },
        "ru": {
            "title": "Скоринг лидов в Salesforce (lead scoring) — CRM Scoring",
            "description": "Оценивайте аккаунты из Salesforce, Bitrix24, amoCRM и HubSpot по шкале Hot / Warm / Cold с объяснением от ИИ. Подходит для компаний в Армении и СНГ. Бесплатный старт.",
            "h1": "Скоринг лидов в Salesforce за несколько минут",
            "intro": "CRM Scoring оценивает каждый аккаунт в вашей CRM от 0 до 100, делит их на Hot / Warm / Cold и пишет короткое объяснение для каждого. Отдел продаж сразу видит, кому звонить в первую очередь.",
            "sections": [
                ("Как это работает", [
                    "- Выгрузите аккаунты из Salesforce (Reports → Export) в CSV или Excel.",
                    "- Загрузите файл в CRM Scoring. Обязательны только название компании и сайт; остальные колонки (отрасль, число сотрудников, выручка, страна) делают оценку точнее.",
                    "- Получите балл, группу Hot / Warm / Cold и объяснение от ИИ для каждого аккаунта.",
                    "- На тарифе Pro отправьте результаты обратно в Salesforce в один клик и получайте уведомления в Slack, когда лид становится Hot.",
                ]),
                ("Не пользуетесь Salesforce?", [
                    "В Армении и СНГ многие компании работают в Bitrix24, amoCRM, HubSpot или просто в Excel. CRM Scoring принимает любую выгрузку в CSV или Excel, так что скоринг заработает и у вас.",
                ]),
                ("Почему оценка прозрачная", [
                    "Балл считается по правилам, которые можно проверить: отрасль (25), размер компании (25), выручка (15), технологии (15), география (10), сигнал найма (10). 75 и выше — Hot, 50–74 — Warm, ниже 50 — Cold. ИИ добавляет то, чего не видят правила.",
                ]),
            ],
            "faq": [
                ("Уходят ли мои данные из компании?", "CRM Scoring можно развернуть на своём сервере — данные CRM остаются в вашей инфраструктуре."),
                ("Сколько стоит?", "Тариф Starter бесплатный (10 загрузок по 10 строк). Pro — $20 в месяц или $192 в год, Advanced — $40 в месяц."),
                ("Нужен ли Salesforce?", "Нет. Достаточно CSV или Excel из любой CRM. Подключение Salesforce нужно только для автоматической отправки результатов обратно."),
            ],
        },
        "en": {
            "title": "Salesforce Lead Scoring with AI — CRM Scoring",
            "description": "Score Salesforce accounts Hot / Warm / Cold with a transparent rule-based score and an AI reason for each. Works with any CRM export. Free to start.",
            "h1": "Salesforce lead scoring in minutes",
            "intro": "CRM Scoring scores every account in your CRM from 0 to 100, sorts them into Hot / Warm / Cold and writes a short reason for each, so your reps know who to call first.",
            "sections": [
                ("How it works", [
                    "- Export your accounts from Salesforce (Reports → Export) as CSV or Excel.",
                    "- Upload the file to CRM Scoring. Only company name and website are required; industry, employees, revenue and country make the score sharper.",
                    "- Get a score, a Hot / Warm / Cold bucket and an AI rationale for every account.",
                    "- On Pro, push the results back to Salesforce in one click and get a Slack alert the moment a lead turns Hot.",
                ]),
                ("Not on Salesforce?", [
                    "CRM Scoring takes any CSV or Excel export — HubSpot, Bitrix24, amoCRM, Pipedrive or a plain spreadsheet.",
                ]),
                ("A score you can check", [
                    "The score comes from weighted rules you can see: industry (25), company size (25), revenue (15), tech stack (15), geography (10), hiring signal (10). 75+ is Hot, 50–74 Warm, below 50 Cold. The AI note adds what rules can't see.",
                ]),
            ],
            "faq": [
                ("Does my CRM data leave my company?", "CRM Scoring can be self-hosted, so your CRM data stays in your own infrastructure."),
                ("How much does it cost?", "Starter is free (10 uploads of 10 rows). Pro is $20/month or $192/year; Advanced is $40/month."),
                ("Do I need Salesforce?", "No. Any CSV or Excel export works. The Salesforce connection is only for pushing scores back automatically."),
            ],
        },
    },
    "ai-lead-scoring": {
        "hy": {
            "title": "AI լիդերի գնահատման գործիք — CRM Scoring",
            "description": "Արհեստական բանականությամբ լիդերի գնահատում հայկական ընկերությունների համար։ Hot / Warm / Cold դասակարգում, բացատրություն յուրաքանչյուր հաճախորդի համար, հայերեն, ռուսերեն և անգլերեն։",
            "h1": "AI լիդերի գնահատում, որը բացատրում է իր որոշումը",
            "intro": "Շատ AI գործիքներ տալիս են միավոր, բայց չեն ասում՝ ինչու։ CRM Scoring-ը միավորում է ստուգելի կանոններ և AI վերլուծություն, որպեսզի վաճառքի թիմը վստահի արդյունքին։",
            "sections": [
                ("Կանոններ + AI", [
                    "- Կանոնները գնահատում են այն, ինչ հայտնի է՝ ոլորտ, չափ, եկամուտ, տեխնոլոգիաներ, երկիր։",
                    "- AI-ն (Claude) ավելացնում է կարճ բացատրություն և նկատում այն, ինչ կանոնները չեն տեսնում՝ նոր ներդրումներ, ակտիվ աշխատանքի ընդունում, մրցակիցների գործիքներ։",
                    "- Յուրաքանչյուր հաշիվ ստանում է Hot / Warm / Cold պիտակ և մեկ նախադասություն՝ ինչու։",
                ]),
                ("Ում համար է", [
                    "- Վաճառքի թիմեր, որոնք ունեն հարյուրավոր կամ հազարավոր լիդեր և ժամանակ չունեն բոլորին զանգելու։",
                    "- IT և B2B ընկերություններ Հայաստանում, որոնք վաճառում են արտերկրում։",
                    "- Գործակալություններ, որոնք աշխատում են մի քանի հաճախորդի CRM-ի հետ (Advanced պլան)։",
                ]),
                ("Երեք լեզվով", [
                    "Ինտերֆեյսը և բացատրությունները հասանելի են հայերեն, ռուսերեն և անգլերեն։",
                ]),
            ],
            "faq": [
                ("Ո՞ր AI-ն է օգտագործվում", "Բացատրությունները գրում է Anthropic-ի Claude մոդելը։ Միավորը հաշվարկվում է կանոններով, ուստի AI-ն չի կարող «հորինել» գնահատականը։"),
                ("Որքա՞ն ժամանակ է պահանջվում", "Ֆայլը վերբեռնելուց հետո արդյունքները պատրաստ են մոտ մեկ րոպեում։"),
                ("Կարո՞ղ եմ փորձել անվճար", "Այո՝ Starter պլանն անվճար է և առանց քարտի։"),
            ],
        },
        "ru": {
            "title": "Инструмент AI-скоринга лидов — CRM Scoring",
            "description": "Скоринг лидов с искусственным интеллектом для компаний Армении и СНГ: Hot / Warm / Cold и объяснение для каждого клиента. На русском, армянском и английском.",
            "h1": "AI-скоринг лидов, который объясняет свои решения",
            "intro": "Многие AI-инструменты выдают балл, но не говорят почему. CRM Scoring сочетает проверяемые правила и анализ ИИ, чтобы отдел продаж доверял результату.",
            "sections": [
                ("Правила + ИИ", [
                    "- Правила оценивают известное: отрасль, размер, выручку, технологии, страну.",
                    "- ИИ (Claude) добавляет короткое объяснение и замечает то, чего не видят правила: новые инвестиции, активный найм, инструменты конкурентов.",
                    "- Каждый аккаунт получает метку Hot / Warm / Cold и одно предложение — почему.",
                ]),
                ("Для кого", [
                    "- Отделы продаж с сотнями и тысячами лидов, которым некогда звонить всем.",
                    "- IT и B2B-компании в Армении и СНГ, продающие на внешние рынки.",
                    "- Агентства, работающие с CRM нескольких клиентов (тариф Advanced).",
                ]),
                ("На трёх языках", [
                    "Интерфейс и объяснения доступны на русском, армянском и английском.",
                ]),
            ],
            "faq": [
                ("Какой ИИ используется?", "Объяснения пишет модель Claude от Anthropic. Сам балл считается по правилам, поэтому ИИ не может «придумать» оценку."),
                ("Сколько времени это занимает?", "После загрузки файла результаты готовы примерно за минуту."),
                ("Можно попробовать бесплатно?", "Да, тариф Starter бесплатный и без карты."),
            ],
        },
        "en": {
            "title": "AI Lead Scoring Tool That Explains Every Score — CRM Scoring",
            "description": "AI lead scoring that combines checkable rules with an AI rationale for every account. Hot / Warm / Cold in a minute. Self-hosted option, free to start.",
            "h1": "An AI lead scoring tool that shows its reasoning",
            "intro": "Most AI scoring tools give you a number and no reason. CRM Scoring combines rules you can check with an AI note for every account, so your team trusts the ranking.",
            "sections": [
                ("Rules + AI", [
                    "- Rules score what's known: industry, size, revenue, tech stack, country.",
                    "- The AI (Claude) adds a one-line rationale and spots what rules miss: new funding, active hiring, competitor tools.",
                    "- Every account gets Hot / Warm / Cold and a sentence on why.",
                ]),
                ("Who it's for", [
                    "- Sales teams with hundreds or thousands of leads and no time to call them all.",
                    "- B2B and IT companies selling internationally.",
                    "- Agencies scoring CRM data for several clients (Advanced plan).",
                ]),
            ],
            "faq": [
                ("Which AI does it use?", "Rationales are written by Anthropic's Claude. The score itself is rule-based, so the AI can't invent a rating."),
                ("How long does it take?", "Results are ready about a minute after you upload the file."),
                ("Can I try it free?", "Yes. Starter is free, no card needed."),
            ],
        },
    },
    "lead-scoring-template": {
        "hy": {
            "title": "Լիդերի գնահատման ձևանմուշ (Excel / CSV) — անվճար",
            "description": "Ներբեռնեք անվճար լիդերի գնահատման ձևանմուշ՝ սյունակներով և կշիռներով։ Լրացրեք Excel-ում և ստացեք Hot / Warm / Cold գնահատում մեկ րոպեում։",
            "h1": "Լիդերի գնահատման ձևանմուշ՝ անվճար",
            "intro": "Ներբեռնեք պատրաստի CSV ձևանմուշը, բացեք Excel-ում կամ Google Sheets-ում, լրացրեք ձեր հաճախորդներով և վերբեռնեք CRM Scoring-ում՝ ավտոմատ գնահատման համար։",
            "download": "Ներբեռնել ձևանմուշը (CSV)",
            "sections": [
                ("Սյունակները", [
                    "- company_name՝ ընկերության անունը (պարտադիր)",
                    "- domain՝ կայքը, օրինակ example.am (պարտադիր)",
                    "- contact_name, contact_title՝ կոնտակտային անձը և պաշտոնը",
                    "- industry՝ ոլորտը, employees՝ աշխատակիցների թիվը, revenue՝ տարեկան եկամուտը (USD), country՝ երկիրը",
                ]),
                ("Կշիռները (100 միավոր)", []),
            ],
            "table": [("Չափանիշ", "Միավոր"), ("Ոլորտ", "25"), ("Ընկերության չափ", "25"), ("Եկամուտ", "15"), ("Տեխնոլոգիաներ", "15"), ("Աշխարհագրություն", "10"), ("Աշխատանքի ընդունում", "10")],
            "after_table": "75 և ավելի՝ Hot, 50–74՝ Warm, 50-ից ցածր՝ Cold։ Կարող եք հաշվել ձեռքով Excel-ում, կամ վերբեռնել ֆայլը և ստանալ միավորներն ու AI բացատրությունները ավտոմատ։",
            "faq": [
                ("Կարո՞ղ եմ օգտագործել իմ սեփական սյունակները", "Այո։ CRM Scoring-ը ճանաչում է տարածված անվանումներ (company, website, job_title, company_size և այլն)։"),
                ("Աշխատո՞ւմ է Bitrix24-ի կամ amoCRM-ի արտահանման հետ", "Այո, եթե ֆայլում կա ընկերության անունը և կայքը։"),
            ],
        },
        "ru": {
            "title": "Шаблон скоринга лидов (Excel / CSV) — бесплатно",
            "description": "Скачайте бесплатный шаблон скоринга лидов с колонками и весами. Заполните в Excel и получите оценку Hot / Warm / Cold за минуту.",
            "h1": "Шаблон скоринга лидов — бесплатно",
            "intro": "Скачайте готовый CSV-шаблон, откройте в Excel или Google Таблицах, заполните своими клиентами и загрузите в CRM Scoring для автоматической оценки.",
            "download": "Скачать шаблон (CSV)",
            "sections": [
                ("Колонки", [
                    "- company_name — название компании (обязательно)",
                    "- domain — сайт, например example.am (обязательно)",
                    "- contact_name, contact_title — контактное лицо и должность",
                    "- industry — отрасль, employees — число сотрудников, revenue — годовая выручка (USD), country — страна",
                ]),
                ("Веса (100 баллов)", []),
            ],
            "table": [("Критерий", "Баллы"), ("Отрасль", "25"), ("Размер компании", "25"), ("Выручка", "15"), ("Технологии", "15"), ("География", "10"), ("Сигнал найма", "10")],
            "after_table": "75 и выше — Hot, 50–74 — Warm, ниже 50 — Cold. Можно посчитать вручную в Excel или загрузить файл и получить баллы и объяснения ИИ автоматически.",
            "faq": [
                ("Можно использовать свои названия колонок?", "Да. CRM Scoring распознаёт распространённые названия (company, website, job_title, company_size и другие)."),
                ("Подойдёт выгрузка из Bitrix24 или amoCRM?", "Да, если в файле есть название компании и сайт."),
            ],
        },
        "en": {
            "title": "Free Lead Scoring Template (Excel / CSV) — CRM Scoring",
            "description": "Download a free lead scoring template with columns and weights. Fill it in Excel or Google Sheets and get Hot / Warm / Cold scores in a minute.",
            "h1": "Free lead scoring template",
            "intro": "Download the ready-made CSV template, open it in Excel or Google Sheets, fill in your accounts and upload it to CRM Scoring to score them automatically.",
            "download": "Download the template (CSV)",
            "sections": [
                ("The columns", [
                    "- company_name — company name (required)",
                    "- domain — website, e.g. example.com (required)",
                    "- contact_name, contact_title — contact person and role",
                    "- industry, employees, revenue (annual, USD), country",
                ]),
                ("The weights (100 points)", []),
            ],
            "table": [("Criterion", "Points"), ("Industry", "25"), ("Company size", "25"), ("Revenue", "15"), ("Tech stack", "15"), ("Geography", "10"), ("Hiring signal", "10")],
            "after_table": "75+ is Hot, 50–74 Warm, below 50 Cold. Score it by hand in a spreadsheet, or upload the file and get the scores and AI rationales automatically.",
            "faq": [
                ("Can I use my own column names?", "Yes. CRM Scoring recognises common names such as company, website, job_title and company_size."),
                ("Does it work with a HubSpot or Pipedrive export?", "Yes, as long as the file has a company name and website."),
            ],
        },
    },
}

STYLE = """
  :root { --bg:#f6f1e6; --bg-alt:#fffcf5; --text-h:#211b12; --text:#6b6152; --text-muted:#8a7e6d; --border:#e6dbc3; --accent:#b3401f; --hot:#c53a2c; --warm:#a8710f; --cold:#5b6472; }
  @media (prefers-color-scheme: dark) { :root { --bg:#18130c; --bg-alt:#211a11; --text-h:#f4ead9; --text:#b6a993; --text-muted:#8d8069; --border:#382d1e; --accent:#e37a4c; --hot:#ea6a53; --warm:#dba43b; --cold:#8b93a3; } }
  * { box-sizing: border-box; }
  body { margin:0; font-family:"IBM Plex Sans", system-ui, sans-serif; background:var(--bg); color:var(--text); line-height:1.65; }
  h1, h2 { font-family:"Fraunces", ui-serif, Georgia, serif; color:var(--text-h); line-height:1.25; }
  h1 { font-size:2rem; margin:8px 0 12px; } h2 { font-size:1.3rem; margin-top:36px; }
  .wrap { max-width:760px; margin:0 auto; padding:0 24px; }
  header.nav { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:20px 0; flex-wrap:wrap; }
  .logo { display:flex; align-items:center; gap:8px; text-decoration:none; }
  .logo-dots { display:flex; gap:3px; } .logo-dots span { width:7px; height:7px; border-radius:999px; display:block; }
  .logo-dots span:nth-child(1){background:var(--hot)} .logo-dots span:nth-child(2){background:var(--warm)} .logo-dots span:nth-child(3){background:var(--cold)}
  .logo-word { font-family:"Fraunces", ui-serif, Georgia, serif; font-weight:600; font-size:1.15rem; color:var(--text-h); }
  .logo-word em { font-style:normal; color:var(--accent); }
  .langs a { margin-left:12px; color:var(--text-muted); font-size:0.9rem; } .langs a[aria-current] { color:var(--accent); font-weight:600; text-decoration:none; }
  main { padding:16px 0 56px; }
  .intro { font-size:1.08rem; color:var(--text-h); }
  ul { padding-left:20px; } li { margin-bottom:6px; }
  .cta { display:inline-block; background:var(--accent); color:#fff; padding:12px 22px; border-radius:8px; text-decoration:none; font-weight:600; margin-top:8px; }
  .cta.secondary { background:transparent; color:var(--accent); border:1px solid var(--accent); }
  .note { font-size:0.88rem; color:var(--text-muted); margin-top:8px; }
  table { border-collapse:collapse; width:100%; max-width:420px; margin:12px 0; background:var(--bg-alt); }
  th, td { border:1px solid var(--border); padding:8px 12px; text-align:left; } th { color:var(--text-h); }
  details { border:1px solid var(--border); background:var(--bg-alt); border-radius:8px; padding:12px 16px; margin-bottom:10px; }
  summary { cursor:pointer; color:var(--text-h); font-weight:600; }
  footer { border-top:1px solid var(--border); padding:24px 0 40px; font-size:0.9rem; color:var(--text-muted); }
  a { color:var(--accent); }
"""


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def url(lang: str, slug: str) -> str:
    return f"{SITE}/{lang}/{slug}.html"


def render_blocks(lines: list[str]) -> str:
    out, items = [], []
    for line in lines + [""]:
        if line.startswith("- "):
            items.append(f"<li>{esc(line[2:])}</li>")
            continue
        if items:
            out.append("<ul>" + "".join(items) + "</ul>")
            items = []
        if line:
            out.append(f"<p>{esc(line)}</p>")
    return "\n".join(out)


def render(slug: str, lang: str) -> str:
    page, ui = PAGES[slug][lang], UI[lang]
    app = f"{SITE}/?lang={lang}#pricing"
    alternates = "\n".join(
        f'<link rel="alternate" hreflang="{other}" href="{url(other, slug)}" />' for other in LANGS
    ) + f'\n<link rel="alternate" hreflang="x-default" href="{url("en", slug)}" />'
    langs = "".join(
        f'<a href="../{other}/{slug}.html" hreflang="{other}"'
        + (' aria-current="page"' if other == lang else "")
        + f">{LANG_NAMES[other]}</a>"
        for other in LANGS
    )
    body = []
    for heading, lines in page["sections"]:
        body.append(f"<h2>{esc(heading)}</h2>\n{render_blocks(lines)}")
    if page.get("table"):
        head, *rows = page["table"]
        body.append(
            "<table><thead><tr>" + "".join(f"<th>{esc(c)}</th>" for c in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in rows)
            + "</tbody></table>"
        )
        body.append(f"<p>{esc(page['after_table'])}</p>")
    download = (
        f'<p><a class="cta secondary" href="../assets/lead-scoring-template.csv" download>{esc(page["download"])}</a></p>'
        if page.get("download") else ""
    )
    faq = "\n".join(
        f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>" for q, a in page["faq"]
    )
    faq_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in page["faq"]
            ],
        },
        ensure_ascii=False,
    )
    more = " · ".join(
        f'<a href="{other}.html">{esc(PAGES[other][lang]["h1"])}</a>' for other in PAGES if other != slug
    )
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(page["title"])}</title>
<meta name="description" content="{esc(page["description"])}" />
<link rel="canonical" href="{url(lang, slug)}" />
{alternates}
<meta property="og:type" content="article" />
<meta property="og:site_name" content="CRM Scoring" />
<meta property="og:locale" content="{OG_LOCALE[lang]}" />
<meta property="og:url" content="{url(lang, slug)}" />
<meta property="og:title" content="{esc(page["title"])}" />
<meta property="og:description" content="{esc(page["description"])}" />
<meta property="og:image" content="{SITE}/assets/og-image.png" />
<meta name="twitter:card" content="summary_large_image" />
<link rel="icon" href="../assets/app-icon.png" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet" />
<style>{STYLE}</style>
<script type="application/ld+json">{faq_ld}</script>
</head>
<body>
<div class="wrap">
  <header class="nav">
    <a class="logo" href="../index.html?lang={lang}" aria-label="CRM Scoring — {esc(ui["home"])}"><span class="logo-dots"><span></span><span></span><span></span></span><span class="logo-word">CRM <em>Scoring</em></span></a>
    <nav class="langs">{langs}</nav>
  </header>
  <main>
    <h1>{esc(page["h1"])}</h1>
    <p class="intro">{esc(page["intro"])}</p>
    {download}
    <p><a class="cta" href="{app}">{esc(ui["cta"])}</a></p>
    <p class="note">{esc(ui["cta_note"])}</p>
    {chr(10).join(body)}
    <h2>{esc(ui["faq"])}</h2>
    {faq}
    <p><a class="cta" href="{app}">{esc(ui["cta"])}</a></p>
    <h2>{esc(ui["more"])}</h2>
    <p>{more}</p>
  </main>
  <footer>&copy; 2026 CRM Scoring · {esc(ui["contact"])} <a href="mailto:hello@crmscoring.com">hello@crmscoring.com</a> · <a href="../terms.html">Terms</a> · <a href="../privacy.html">Privacy</a></footer>
</div>
</body>
</html>
"""


def sitemap() -> str:
    entries = [f"  <url><loc>{SITE}/</loc></url>"]
    for slug in PAGES:
        for lang in LANGS:
            links = "".join(
                f'<xhtml:link rel="alternate" hreflang="{other}" href="{url(other, slug)}"/>' for other in LANGS
            )
            entries.append(f"  <url><loc>{url(lang, slug)}</loc>{links}</url>")
    for page in ("terms.html", "privacy.html", "refunds.html", "guardrails.html"):
        entries.append(f"  <url><loc>{SITE}/{page}</loc></url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )


def main() -> None:
    for slug in PAGES:
        for lang in LANGS:
            out = DOCS / lang / f"{slug}.html"
            out.parent.mkdir(exist_ok=True)
            out.write_text(render(slug, lang), encoding="utf-8")
    (DOCS / "sitemap.xml").write_text(sitemap(), encoding="utf-8")
    (DOCS / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nDisallow: /app.html\nDisallow: /thank-you.html\nDisallow: /login.html\n\nSitemap: {SITE}/sitemap.xml\n",
        encoding="utf-8",
    )
    print(f"Built {len(PAGES) * len(LANGS)} pages, sitemap.xml and robots.txt in {DOCS}")


if __name__ == "__main__":
    main()
