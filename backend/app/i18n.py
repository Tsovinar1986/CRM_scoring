"""Server messages in Armenian and Russian, for the app's language switcher.

The frontend sends Accept-Language: en, hy or ru. main.py translates every
HTTPException detail through translate() (and a few routes translate their
own status messages), so the messages people see match the language they
picked. Text without a translation here is left in English. Messages with
variable parts are matched by pattern.
"""

import re

from fastapi import Request

SUPPORTED = ("en", "hy", "ru")


def request_lang(request: Request) -> str:
    """The first supported language in the request's Accept-Language, else English."""
    for part in request.headers.get("accept-language", "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in SUPPORTED:
            return code
    return "en"


# English text -> {language: translation}
_EXACT: dict[str, dict[str, str]] = {
    "Lead not found": {"hy": "Լիդը չի գտնվել", "ru": "Лид не найден"},
    "Couldn't connect to the payment service.": {
        "hy": "Չհաջողվեց կապ հաստատել վճարային ծառայության հետ։",
        "ru": "Не удалось подключиться к платёжному сервису.",
    },
    "Your free trial's uploads are used up. Subscribe to Pro or Advanced to keep scoring leads.": {
        "hy": "Ձեր անվճար փորձաշրջանի վերբեռնումներն սպառվել են։ Բաժանորդագրվեք Pro կամ Advanced պլանին՝ լիդերի գնահատումը շարունակելու համար։",
        "ru": "Загрузки бесплатного пробного периода закончились. Оформите подписку Pro или Advanced, чтобы продолжить оценку лидов.",
    },
    "Starter's free upload allowance is used up. Upgrade to Pro or Advanced at /api/billing/checkout and set LICENSE_KEY in .env, or sign up for your own workspace at /api/accounts/signup.": {
        "hy": "Starter պլանի անվճար վերբեռնումներն սպառվել են։ Անցեք Pro կամ Advanced պլանին և նշեք LICENSE_KEY-ը .env ֆայլում, կամ գրանցեք ձեր սեփական աշխատանքային տարածքը։",
        "ru": "Бесплатные загрузки плана Starter закончились. Перейдите на Pro или Advanced и укажите LICENSE_KEY в .env, либо зарегистрируйте собственное рабочее пространство.",
    },
    "Webhooks aren't configured on this deployment.": {
        "hy": "Վեբհուկերը կարգավորված չեն այս սերվերում։",
        "ru": "Вебхуки на этом сервере не настроены.",
    },
    "This workspace has no login to change.": {
        "hy": "Այս աշխատանքային տարածքը մուտքի տվյալներ չունի, որոնք հնարավոր լինի փոխել։",
        "ru": "У этого рабочего пространства нет данных для входа, которые можно изменить.",
    },
    "This workspace has no active subscription.": {
        "hy": "Այս աշխատանքային տարածքը ակտիվ բաժանորդագրություն չունի։",
        "ru": "У этого рабочего пространства нет активной подписки.",
    },
    "This payment isn't complete yet.": {
        "hy": "Այս վճարումը դեռ ավարտված չէ։",
        "ru": "Этот платёж ещё не завершён.",
    },
    "That reset link is invalid or has expired.": {
        "hy": "Վերականգնման հղումն անվավեր է կամ ժամկետանց։",
        "ru": "Ссылка для сброса недействительна или устарела.",
    },
    "That password isn't correct.": {
        "hy": "Գաղտնաբառը սխալ է։",
        "ru": "Неверный пароль.",
    },
    "Subscription isn't active.": {
        "hy": "Բաժանորդագրությունն ակտիվ չէ։",
        "ru": "Подписка не активна.",
    },
    "Subscription is for an unknown plan.": {
        "hy": "Բաժանորդագրությունն անհայտ պլանի համար է։",
        "ru": "Подписка оформлена на неизвестный план.",
    },
    "Onboarding new client workspaces requires an Advanced license on this deployment.": {
        "hy": "Նոր հաճախորդների աշխատանքային տարածքներ ավելացնելու համար այս սերվերում անհրաժեշտ է Advanced լիցենզիա։",
        "ru": "Для подключения новых клиентских рабочих пространств на этом сервере нужна лицензия Advanced.",
    },
    "No leads found in file.": {
        "hy": "Ֆայլում լիդեր չեն գտնվել։",
        "ru": "В файле не найдено лидов.",
    },
    "No customer rows found in file.": {
        "hy": "Ֆայլում հաճախորդների տողեր չեն գտնվել։",
        "ru": "В файле не найдено строк с клиентами.",
    },
    "File must include at least a company name and a domain/website column.": {
        "hy": "Ֆայլը պետք է պարունակի առնվազն ընկերության անվանման և դոմենի/կայքի սյունակներ։",
        "ru": "В файле должны быть как минимум столбцы с названием компании и доменом/сайтом.",
    },
    "Missing webhook signature.": {
        "hy": "Վեբհուկի ստորագրությունը բացակայում է։",
        "ru": "Отсутствует подпись вебхука.",
    },
    "Invalid webhook signature.": {
        "hy": "Վեբհուկի ստորագրությունն անվավեր է։",
        "ru": "Недействительная подпись вебхука.",
    },
    "License signing key not configured on this deployment.": {
        "hy": "Լիցենզիայի ստորագրման բանալին կարգավորված չէ այս սերվերում։",
        "ru": "Ключ подписи лицензий на этом сервере не настроен.",
    },
    "Invalid API key": {
        "hy": "Անվավեր API բանալի",
        "ru": "Недействительный API-ключ",
    },
    "Incorrect email or password.": {
        "hy": "Էլ. փոստը կամ գաղտնաբառը սխալ է։",
        "ru": "Неверная почта или пароль.",
    },
    "Free trials aren't offered on this deployment.": {
        "hy": "Այս սերվերում անվճար փորձաշրջան չի տրամադրվում։",
        "ru": "На этом сервере бесплатный пробный период не предоставляется.",
    },
    "Checkout isn't configured on this deployment.": {
        "hy": "Վճարումը կարգավորված չէ այս սերվերում։",
        "ru": "Оплата на этом сервере не настроена.",
    },
    "Authorization header must be 'Bearer <api-key>'": {
        "hy": "Authorization վերնագիրը պետք է լինի 'Bearer <api-key>' ձևաչափով",
        "ru": "Заголовок Authorization должен иметь вид 'Bearer <api-key>'",
    },
    "An account with that email already exists.": {
        "hy": "Այդ էլ. հասցեով հաշիվ արդեն կա։",
        "ru": "Аккаунт с такой почтой уже существует.",
    },
    "Account settings are only available for signed-in workspaces.": {
        "hy": "Հաշվի կարգավորումները հասանելի են միայն մուտք գործած աշխատանքային տարածքների համար։",
        "ru": "Настройки аккаунта доступны только для рабочих пространств с выполненным входом.",
    },
    "If that email has an account, a reset link is on its way.": {
        "hy": "Եթե այդ էլ. հասցեով հաշիվ կա, վերականգնման հղումն արդեն ճանապարհին է։",
        "ru": "Если на этот адрес есть аккаунт, ссылка для сброса уже в пути.",
    },
    "Password must be at least 8 characters long.": {
        "hy": "Գաղտնաբառը պետք է լինի առնվազն 8 նիշ։",
        "ru": "Пароль должен содержать не менее 8 символов.",
    },
    "Password is too long.": {
        "hy": "Գաղտնաբառը չափազանց երկար է։",
        "ru": "Пароль слишком длинный.",
    },
    "Password must include at least one uppercase letter.": {
        "hy": "Գաղտնաբառը պետք է պարունակի առնվազն մեկ մեծատառ։",
        "ru": "Пароль должен содержать хотя бы одну заглавную букву.",
    },
    "Password must include at least one lowercase letter.": {
        "hy": "Գաղտնաբառը պետք է պարունակի առնվազն մեկ փոքրատառ։",
        "ru": "Пароль должен содержать хотя бы одну строчную букву.",
    },
    "Password must include at least one number.": {
        "hy": "Գաղտնաբառը պետք է պարունակի առնվազն մեկ թիվ։",
        "ru": "Пароль должен содержать хотя бы одну цифру.",
    },
    "Password must include at least one symbol (e.g. !@#$%).": {
        "hy": "Գաղտնաբառը պետք է պարունակի առնվազն մեկ հատուկ նշան (օր.՝ !@#$%)։",
        "ru": "Пароль должен содержать хотя бы один спецсимвол (например, !@#$%).",
    },
}

# (pattern, {language: template}); templates use the pattern's groups as {0}, {1}...
_PATTERNS: list[tuple[re.Pattern[str], dict[str, str]]] = [
    (
        re.compile(r"^Could not parse file: (.+)$", re.S),
        {"hy": "Չհաջողվեց կարդալ ֆայլը՝ {0}", "ru": "Не удалось прочитать файл: {0}"},
    ),
    (
        re.compile(r"^Unsupported file type -- must be one of: (.+)\.$"),
        {"hy": "Ֆայլի տեսակը չի աջակցվում․ թույլատրելի են՝ {0}։", "ru": "Неподдерживаемый тип файла — допустимы: {0}."},
    ),
    (
        re.compile(r"^File is too large -- max (\d+)MB per upload\.$"),
        {"hy": "Ֆայլը չափազանց մեծ է․ առավելագույնը {0} ՄԲ մեկ վերբեռնման համար։", "ru": "Файл слишком большой — не более {0} МБ за одну загрузку."},
    ),
    (
        re.compile(r"^File has (\d+) rows -- max (\d+) per upload\. Split it into smaller files\.$"),
        {
            "hy": "Ֆայլն ունի {0} տող․ առավելագույնը {1} մեկ վերբեռնման համար։ Բաժանեք այն ավելի փոքր ֆայլերի։",
            "ru": "В файле {0} строк — не более {1} за одну загрузку. Разбейте его на файлы поменьше.",
        },
    ),
    (
        re.compile(r"^Created new Salesforce Lead (\S+) for (.+)\.$"),
        {"hy": "Salesforce-ում ստեղծվեց նոր լիդ {0}՝ {1}։", "ru": "В Salesforce создан новый лид {0} для {1}."},
    ),
    (
        re.compile(r"^Updated existing Salesforce Lead (\S+) for (.+)\.$"),
        {"hy": "Salesforce-ում թարմացվեց լիդ {0}՝ {1}։", "ru": "В Salesforce обновлён лид {0} для {1}."},
    ),
]


def translate(text: str, lang: str) -> str:
    """text in lang if there's a translation, else unchanged."""
    if lang == "en" or not isinstance(text, str):
        return text
    exact = _EXACT.get(text)
    if exact and lang in exact:
        return exact[lang]
    for pattern, templates in _PATTERNS:
        match = pattern.match(text)
        if match and lang in templates:
            return templates[lang].format(*match.groups())
    return text
