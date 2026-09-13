from __future__ import annotations

LANGUAGES = {"EN": "English", "LT": "Lietuvių", "PL": "Polski", "UA": "Українська", "RU": "Русский", "NO": "Norsk", "FR": "Français", "DE": "Deutsch", "IT": "Italiano", "ES": "Español"}
_CODES = tuple(LANGUAGES)
_ROWS = {
    "language": ("Language", "Kalba", "Język", "Мова", "Язык", "Språk", "Langue", "Sprache", "Lingua", "Idioma"),
    "interval": ("Click Interval", "Paspaudimų intervalas", "Interwał kliknięć", "Інтервал натискань", "Интервал нажатий", "Klikkintervall", "Intervalle de clic", "Klickintervall", "Intervallo clic", "Intervalo de clic"),
    "options": ("Click Options", "Paspaudimo parinktys", "Opcje kliknięcia", "Параметри натискання", "Параметры нажатия", "Klikkalternativer", "Options de clic", "Klickoptionen", "Opzioni clic", "Opciones de clic"),
    "location": ("Click Location", "Paspaudimo vieta", "Miejsce kliknięcia", "Місце натискання", "Место нажатия", "Klikksted", "Emplacement du clic", "Klickposition", "Posizione clic", "Ubicación del clic"),
    "repeat": ("Repeat", "Kartojimas", "Powtarzanie", "Повторення", "Повтор", "Gjenta", "Répéter", "Wiederholen", "Ripeti", "Repetir"),
    "until_stopped": ("Repeat until stopped", "Kartoti iki sustabdymo", "Powtarzaj do zatrzymania", "Повторювати до зупинки", "Повторять до остановки", "Gjenta til stoppet", "Répéter jusqu’à l’arrêt", "Bis zum Stoppen wiederholen", "Ripeti fino all’arresto", "Repetir hasta detener"),
    "current": ("Current cursor position", "Dabartinė žymeklio vieta", "Bieżąca pozycja kursora", "Поточна позиція курсора", "Текущая позиция курсора", "Gjeldende markørposisjon", "Position actuelle du curseur", "Aktuelle Cursorposition", "Posizione corrente del cursore", "Posición actual del cursor"),
    "fixed": ("Fixed position:", "Fiksuota vieta:", "Stała pozycja:", "Фіксована позиція:", "Фиксированная позиция:", "Fast posisjon:", "Position fixe :", "Feste Position:", "Posizione fissa:", "Posición fija:"),
    "start": ("Start", "Paleisti", "Start", "Запустити", "Запустить", "Start", "Démarrer", "Starten", "Avvia", "Iniciar"),
    "stop": ("Stop", "Sustabdyti", "Zatrzymaj", "Зупинити", "Остановить", "Stopp", "Arrêter", "Stoppen", "Arresta", "Detener"),
    "stop_all": ("Stop All", "Sustabdyti viską", "Zatrzymaj wszystko", "Зупинити все", "Остановить всё", "Stopp alt", "Tout arrêter", "Alles stoppen", "Arresta tutto", "Detener todo"),
    "settings": ("Settings…", "Nustatymai…", "Ustawienia…", "Налаштування…", "Настройки…", "Innstillinger…", "Paramètres…", "Einstellungen…", "Impostazioni…", "Ajustes…"),
    "hotkey": ("Hotkey", "Spartusis klavišas", "Skrót", "Гаряча клавіша", "Горячая клавиша", "Hurtigtast", "Raccourci", "Tastenkürzel", "Scorciatoia", "Atajo"),
    "macros": ("Macros", "Makrokomandos", "Makra", "Макроси", "Макросы", "Makroer", "Macros", "Makros", "Macro", "Macros"),
    "controller": ("Controller", "Valdiklis", "Kontroler", "Контролер", "Контроллер", "Kontroller", "Manette", "Controller", "Controller", "Mando"),
    "about": ("About", "Apie", "O programie", "Про програму", "О программе", "Om", "À propos", "Über", "Informazioni", "Acerca de"),
    "idle": ("Idle", "Neveikia", "Bezczynny", "Бездіяльний", "Ожидание", "Inaktiv", "Inactif", "Inaktiv", "Inattivo", "Inactivo"),
}
CATALOGS = {code: {key: row[index] for key, row in _ROWS.items()} for index, code in enumerate(_CODES)}


def translate(language: str, key: str) -> str:
    return CATALOGS.get(language, CATALOGS["EN"]).get(key, key)
