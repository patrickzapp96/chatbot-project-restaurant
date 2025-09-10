from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import smtplib
from email.message import EmailMessage
import re
from icalendar import Calendar, Event
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Globale Variable zur Speicherung des Konversationsstatus
user_states = {}

# FAQ-Datenbank für ein Restaurant
faq_db = {
    "fragen": [
        {
            "id": 1,
            "kategorie": "Öffnungszeiten",
            "titel": "Öffnungszeiten",
            "keywords": ["öffnungszeiten", "wann", "geöffnet", "offen", "arbeitszeit"],
            "antwort": "Wir sind Montag bis Samstag von 12:00 bis 22:00 Uhr und Sonntag von 12:00 bis 21:00 Uhr für Sie geöffnet. Die Küche schließt 30 Minuten vor Ende der Öffnungszeiten."
        },
        {
            "id": 2,
            "kategorie": "Reservierung",
            "titel": "Tisch reservieren",
            "keywords": ["tisch", "reservieren", "buchen", "platz", "reservierung", "online"],
            "antwort": "Sie können durch die Eingabe von 'tisch reservieren' einen Tisch reservieren oder uns direkt unter 030-123456 anrufen."
        },
        {
            "id": 3,
            "kategorie": "Allgemein",
            "titel": "Adresse",
            "keywords": ["adresse", "wo", "anschrift", "finden", "lage"],
            "antwort": "Unsere Adresse lautet: Musterstraße 12, 10115 Berlin. Wir befinden uns in der Nähe des Stadtparks."
        },
        {
            "id": 4,
            "kategorie": "Speisekarte",
            "titel": "Speisekarte und Preise",
            "keywords": ["speisekarte", "menü", "gerichte", "essen", "karte", "preise", "kosten"],
            "antwort": "Unsere Speisekarte finden Sie auf unserer Website. Wir bieten eine breite Auswahl an Gerichten zu fairen Preisen an."
        },
        {
            "id": 5,
            "kategorie": "Zahlung",
            "titel": "Zahlungsmethoden",
            "keywords": ["zahlung", "karte", "bar", "visa", "mastercard", "paypal", "kartenzahlung", "kontaktlos", "bezahlen"],
            "antwort": "Sie können bar, mit EC-Karte, Kreditkarte (Visa/Mastercard) und kontaktlos per Handy bezahlen."
        },
        {
            "id": 6,
            "kategorie": "Allgemein",
            "titel": "Parkmöglichkeiten",
            "keywords": ["parkplätze", "parkplatz", "parken", "auto", "stellplatz"],
            "antwort": "Es gibt öffentliche Parkplätze in den umliegenden Straßen. Ein Parkhaus befindet sich nur 5 Gehminuten entfernt."
        },
        {
            "id": 7,
            "kategorie": "Ernährung",
            "titel": "Allergien und Unverträglichkeiten",
            "keywords": ["allergien", "unverträglichkeiten", "vegan", "vegetarisch", "glutenfrei", "laktosefrei"],
            "antwort": "Bitte informieren Sie unser Personal über alle Allergien und Unverträglichkeiten. Wir können viele unserer Gerichte anpassen und bieten auch vegane, vegetarische und glutenfreie Optionen an."
        },
        {
            "id": 8,
            "kategorie": "Allgemein",
            "titel": "Haustiere",
            "keywords": ["hund", "haustier", "tiere"],
            "antwort": "Haustiere sind in unserem Innenbereich leider nicht gestattet. Auf unserer Außenterrasse sind angeleinte Hunde willkommen."
        },
        {
            "id": 9,
            "kategorie": "Produkte",
            "titel": "Gutscheine kaufen",
            "keywords": ["gutschein", "gutscheine", "verschenken", "geschenk"],
            "antwort": "Ja, Sie können bei uns Gutscheine kaufen – das ideale Geschenk für Freunde und Familie!"
        }
    ],
    "fallback": "Das weiß ich leider nicht. Bitte rufen Sie uns direkt unter 030-123456 an, wir helfen Ihnen gerne persönlich weiter."
}

def send_reservation_request(request_data):
    """
    Diese Funktion sendet eine E-Mail mit der Reservierungsanfrage.
    """
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL")

    if not all([sender_email, sender_password, receiver_email]):
        print("E-Mail-Konfiguration fehlt. E-Mail kann nicht gesendet werden.")
        return False

    msg = EmailMessage()
    msg['Subject'] = "Neue Tischreservierung"
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Reply-To'] = request_data.get('email', 'no-reply@example.com')

    # Text der E-Mail
    email_text = f"""
    Hallo Geschäftsführer,
    
    Sie haben eine neue Tischreservierungsanfrage erhalten:
    
    Name: {request_data.get('name', 'N/A')}
    E-Mail: {request_data.get('email', 'N/A')}
    Anzahl Personen: {request_data.get('personen', 'N/A')}
    Datum & Uhrzeit: {request_data.get('date_time', 'N/A')}
    Sonderwünsche: {request_data.get('wunsch', 'N/A')}
    
    Bitte bestätigen Sie diese Reservierung manuell oder kontaktieren Sie den Kunden direkt.
    """
    msg.set_content(email_text)
    
    # Sende die E-Mail
    try:
        with smtplib.SMTP_SSL("smtp.web.de", 465) as smtp:
            smtp.login(sender_email, sender_password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"Fehler beim Senden der E-Mail: {e}")
        return False

# Neue Funktion zum Protokollieren von nicht beantworteten Fragen
def log_unanswered_query(query):
    try:
        with open("unanswered_queries.log", "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] UNANSWERED: {query}\n")
    except Exception as e:
        print(f"Fehler beim Schreiben der Log-Datei: {e}")

@app.route('/api/chat', methods=['POST'])
def chat_handler():
    try:
        if not request.is_json:
            return jsonify({"error": "Fehlende JSON-Nachricht"}), 400

        user_message = request.json.get('message', '').lower()
        user_ip = request.remote_addr
        
        if user_ip not in user_states:
            user_states[user_ip] = {"state": "initial"}
            
        current_state = user_states[user_ip]["state"]
        response_text = faq_db['fallback']

        # Überprüfe den aktuellen Konversationsstatus
        if current_state == "initial":
            
            # WICHTIG: Prüfe zuerst auf Keywords für die Tischreservierung
            if any(keyword in user_message for keyword in ["tisch reservieren", "reservierung tätigen", "platz buchen"]):
                response_text = "Möchten Sie eine Tischreservierung vornehmen? Bitte antworten Sie mit 'Ja' oder 'Nein'."
                user_states[user_ip] = {"state": "waiting_for_confirmation_reservation"}
            else:
                # Führe die einfache Keyword-Suche durch
                cleaned_message = re.sub(r'[^\w\s]', '', user_message)
                user_words = set(cleaned_message.split())
                best_match_score = 0
                found_match = False
                
                for item in faq_db['fragen']:
                    keyword_set = set(item['keywords'])
                    intersection = user_words.intersection(keyword_set)
                    score = len(intersection)
                    
                    if score > best_match_score:
                        best_match_score = score
                        response_text = item['antwort']
                        found_match = True
                
                # Wenn kein Match gefunden wurde, logge die Anfrage und nutze Fallback
                if not found_match:
                    log_unanswered_query(user_message)
                    response_text = faq_db['fallback']

        elif current_state == "waiting_for_confirmation_reservation":
            if user_message in ["ja", "ja, das stimmt", "bestätigen", "ja bitte"]:
                response_text = "Gerne. Wie lautet Ihr vollständiger Name?"
                user_states[user_ip]["state"] = "waiting_for_name"
            elif user_message in ["nein", "abbrechen", "falsch"]:
                response_text = "Die Reservierungsanfrage wurde abgebrochen. Falls Sie die Eingabe korrigieren möchten, beginnen Sie bitte erneut mit 'tisch reservieren'."
                user_states[user_ip]["state"] = "initial"
            else:
                response_text = "Bitte antworten Sie mit 'Ja' oder 'Nein'."
                
        elif current_state == "waiting_for_name":
            user_states[user_ip]["name"] = user_message
            response_text = "Vielen Dank. Wie lautet Ihre E-Mail-Adresse?"
            user_states[user_ip]["state"] = "waiting_for_email"

        elif current_state == "waiting_for_email":
            email_regex = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
            if re.match(email_regex, user_message):
                user_states[user_ip]["email"] = user_message
                response_text = "Für wie viele Personen möchten Sie reservieren?"
                user_states[user_ip]["state"] = "waiting_for_persons"
            else:
                response_text = "Das scheint keine gültige E-Mail-Adresse zu sein. Bitte geben Sie eine korrekte E-Mail-Adresse ein."
        
        elif current_state == "waiting_for_persons":
            try:
                personen_anzahl = int(user_message)
                user_states[user_ip]["personen"] = personen_anzahl
                response_text = "Wann möchten Sie den Tisch reservieren? Bitte geben Sie das Datum und die Uhrzeit im Format **TT.MM.JJJJ HH:MM** ein, z.B. **15.10.2025 19:30**."
                user_states[user_ip]["state"] = "waiting_for_datetime"
            except ValueError:
                response_text = "Bitte geben Sie eine gültige Zahl für die Personenanzahl ein."

        elif current_state == "waiting_for_datetime":
            user_states[user_ip]["date_time"] = user_message
            response_text = "Haben Sie spezielle Wünsche, z.B. einen Tisch am Fenster oder einen Kinderstuhl?"
            user_states[user_ip]["state"] = "waiting_for_wunsch"

        elif current_state == "waiting_for_wunsch":
            user_states[user_ip]["wunsch"] = user_message
            data = user_states[user_ip]
            response_text = (
                f"Bitte überprüfen Sie Ihre Angaben:\n"
                f"Name: {data.get('name', 'N/A')}\n"
                f"E-Mail: {data.get('email', 'N/A')}\n"
                f"Personen: {data.get('personen', 'N/A')}\n"
                f"Datum und Uhrzeit: {data.get('date_time', 'N/A')}\n"
                f"Sonderwünsche: {data.get('wunsch', 'N/A')}\n\n"
                f"Möchten Sie die Anfrage so absenden? Bitte antworten Sie mit 'Ja' oder 'Nein'."
            )
            user_states[user_ip]["state"] = "waiting_for_confirmation"
        
        elif current_state == "waiting_for_confirmation":
            if user_message in ["ja", "ja, das stimmt", "bestätigen", "ja bitte"]:
                request_data = {
                    "name": user_states[user_ip].get("name", "N/A"),
                    "email": user_states[user_ip].get("email", "N/A"),
                    "personen": user_states[user_ip].get("personen", "N/A"),
                    "date_time": user_states[user_ip].get("date_time", "N/A"),
                    "wunsch": user_states[user_ip].get("wunsch", "N/A"),
                }
            
                if send_reservation_request(request_data):
                    response_text = "Vielen Dank! Ihre Reservierungsanfrage wurde erfolgreich übermittelt. Wir werden uns in Kürze bei Ihnen melden."
                else:
                    response_text = "Entschuldigung, es gab ein Problem beim Senden Ihrer Anfrage. Bitte rufen Sie uns direkt an unter 030-123456."
                
                user_states[user_ip]["state"] = "initial"
            
            elif user_message in ["nein", "abbrechen", "falsch"]:
                response_text = "Die Reservierungsanfrage wurde abgebrochen. Falls Sie die Eingabe korrigieren möchten, beginnen Sie bitte erneut mit 'tisch reservieren'."
                user_states[user_ip]["state"] = "initial"
            
            else:
                response_text = "Bitte antworten Sie mit 'Ja' oder 'Nein'."
        
        return jsonify({"reply": response_text})

    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")
        return jsonify({"error": "Interner Serverfehler"}), 500

if __name__ == '__main__':
    app.run(debug=True)
