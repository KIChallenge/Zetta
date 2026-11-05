"""Build corpus/doctors.json from the scraped praxisplan.at profiles.

    uv run scripts/import_doctors.py ../../data/doctors_merged

Keeps Vienna practices of the specialties the user can pick, and only what a plan shows. Private mobiles and
email addresses are left out.
"""

import json
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUTPUT = BACKEND_DIR / "corpus" / "doctors.json"
SOURCE = "https://praxisplan.at"
COST_SOURCE = "https://www.oegk.at/cdscontent/?contentid=10007.870516&portal=oegkportal"

# Name in the source (without the contract in brackets) -> value of the `specialty` fact. No source for dentistry.
SPECIALTIES = {
    "Allgemeinmedizin": "general_practice",
    "Allgemein- und Familienmedizin": "general_practice",
    "Innere Medizin": "internal_medicine",
    "Frauenheilkunde u. Geburtshilfe": "gynaecology",
    "Kinder- u. Jugendheilkunde": "paediatrics",
    "Haut- u. Geschlechtskrankheiten": "dermatology",
    "Augenheilkunde u. Optometrie": "ophthalmology",
    "Hals-, Nasen- u. Ohrenheilkunde": "ent",
    "Orthopädie und Traumatologie": "orthopaedics",
    "Orthopädie u. Orthopädische Chirurgie": "orthopaedics",
}
DAYS = {"Mo": "mon", "Di": "tue", "Mi": "wed", "Do": "thu", "Fr": "fri", "Sa": "sat", "So": "sun"}
VIENNA_POSTAL_CODE = re.compile(r"^1(0[1-9]|1\d|2[0-3])0$")
PHONE = re.compile(r"^\+?[\d ()/-]{6,}$")
CLOCK = re.compile(r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$")
# Only about preventive check-ups, or the absence of any contract: not an insurer.
NOT_INSURERS = {"KEINE", "VU Vorsorgeuntersuchungs-Vertrag"}


def windows(days: list[dict]) -> list[dict] | None:
    """Days with the same times become one window, in the shape of a corpus channel's hours."""
    spans: dict[tuple[str, str], list[str]] = {}
    for day in days:
        for time in day["times"]:
            if day["day"] in DAYS and CLOCK.match(time["from"] or "") and CLOCK.match(time["to"] or ""):
                spans.setdefault((time["from"], time["to"]), []).append(DAYS[day["day"]])
    return [{"days": d, "from": f, "to": t} for (f, t), d in spans.items()] or None


def practice(doctor: dict, ordination: dict) -> dict | None:
    """The record for one practice, or None if a user could not act on it."""
    address = ordination["address"]
    name = re.sub(r"\s*\(.*$", "", ordination["specialization"] or "").strip()
    phones = [p for p in ordination["contact"]["phones"] if PHONE.match(p)]
    coordinates = ordination["coordinates"] or {}
    if not (
        name in SPECIALTIES
        and VIENNA_POSTAL_CODE.match(address["postal_code"] or "")
        and address["street"]
        and phones
        and coordinates.get("lat")
        and coordinates.get("lon")
        and (ordination["url"] or "").startswith("https://")  # shown as a link
    ):
        return None
    return {
        "id": f"{doctor['id']}.{ordination['number']}",  # with a hyphen it would read as a phone number
        "name": doctor["name"],
        "specialty": SPECIALTIES[name],
        "postal_code": address["postal_code"],
        "address": f"{address['street']}, {address['postal_code']} Wien",
        "lat": coordinates["lat"],
        "lon": coordinates["lon"],
        "phone": phones[0],
        "hours": windows(ordination["opening_hours"]["days"]),
        "insurers": [i for i in ordination["insurers"] if i not in NOT_INSURERS],
        "source_url": ordination["url"],
    }


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    profiles = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(sys.argv[1]).glob("*.json"))]
    doctors = [
        record
        for doctor in profiles
        for ordination in doctor["ordinations"]
        if (record := practice(doctor, ordination))
    ]
    doctors.sort(key=lambda d: d["id"])
    scraped_at = max(p["scraped_at"] for p in profiles)
    # One practice per line, so a new import gives a readable diff.
    lines = ",\n".join(json.dumps(d, ensure_ascii=False, separators=(",", ":")) for d in doctors)
    OUTPUT.write_text(
        f'{{"source":"{SOURCE}","cost_source":"{COST_SOURCE}","scraped_at":"{scraped_at}","doctors":[\n{lines}\n]}}\n',
        encoding="utf-8",
    )
    print(f"{len(doctors)} practices from {len(profiles)} profiles -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
