// Menüleistensymbol des Maschinenraums: das zentrale Steuerwerk dieses Rechners.
// Oben die KI-Dienste (Maschinenraum), darunter der Betrieb: Steuerprogramme wie das Stellwerk (starten, anhalten,
// öffnen) und dessen Webapps mit Schaltern, dazu der Weg zur Leitstelle.
// Es verwaltet selbst nichts: KI-Dienste und Steuerprogramme schaltet der Maschinenraum, Webapps das Stellwerk.

import AppKit
import SwiftUI

struct Messwerte: Decodable {
    let speicher_gesamt_gb: Double
    let speicher_belegt_gb: Double
    let swap_belegt_gb: Double?
    let swap_gesamt_gb: Double?
}

struct Dienst: Decodable, Identifiable {
    let kennung: String
    let name: String
    let zustand: String
    let gb_jetzt: Double?
    let bedarf_gb: Double
    let aktiv: Bool
    var id: String { kennung }
    var laeuft: Bool { zustand == "laeuft" || zustand == "startet" || zustand == "stoppt" }
}

struct Leitstelle: Decodable { let zustand: String; let adresse: String? }

struct Steuerprogramm: Decodable, Identifiable {
    let kennung: String
    let name: String
    let zustand: String
    let oberflaeche: String?
    var id: String { kennung }
    var laeuft: Bool { zustand == "laeuft" || zustand == "startet" || zustand == "stoppt" }
}

struct Stand: Decodable {
    let rechner: String
    let messwerte: Messwerte?
    let dienste: [Dienst]
    let betrieb: [Steuerprogramm]
    let leitstelle: Leitstelle
}

// Webapps eines Steuerprogramms, das welche führt (das Stellwerk); andere Programme liefern keine
struct Webapp: Decodable, Identifiable {
    let kennung: String
    let name: String
    let zustand: String
    let oberflaeche: String?
    let gb_jetzt: Double?
    var id: String { kennung }
    var an: Bool { zustand != "aus" && zustand != "gestoert" }
}

struct Webapps: Decodable { let apps: [Webapp] }

@MainActor
final class Modell: ObservableObject {
    @Published var stand: Stand?
    @Published var erreichbar = true
    @Published var arbeitet: Set<String> = []
    @Published var webapps: [String: [Webapp]] = [:]      // je Steuerprogramm seine Webapps
    let basis: URL
    private var zeitgeber: Timer?

    init() {
        let port = Bundle.main.object(forInfoDictionaryKey: "MaschinenraumPort") as? Int ?? 8540
        basis = URL(string: "http://127.0.0.1:\(port)")!
        zeitgeber = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.holen() }
        }
        Task { await holen() }
    }

    func holen() async {
        do {
            let (daten, _) = try await URLSession.shared.data(from: basis.appendingPathComponent("api/stand"))
            stand = try JSONDecoder().decode(Stand.self, from: daten)
            erreichbar = true
        } catch {
            erreichbar = false
        }
        await webappsHolen()
    }

    func webappsHolen() async {
        var neu: [String: [Webapp]] = [:]
        for p in stand?.betrieb ?? [] where p.laeuft {
            guard let o = p.oberflaeche, let url = URL(string: o)?.appendingPathComponent("api/stand") else { continue }
            if let (daten, _) = try? await URLSession.shared.data(from: url), let w = try? JSONDecoder().decode(Webapps.self, from: daten) {
                neu[p.kennung] = w.apps
            }
        }
        webapps = neu
    }

    private func senden(_ url: URL, kopf: String) async {
        var anfrage = URLRequest(url: url)
        anfrage.httpMethod = "POST"
        anfrage.timeoutInterval = 900
        anfrage.setValue("1", forHTTPHeaderField: kopf)
        _ = try? await URLSession.shared.data(for: anfrage)
    }

    func schalten(_ p: Steuerprogramm) async {
        arbeitet.insert("betrieb:" + p.kennung)
        await senden(basis.appendingPathComponent("api/betrieb/\(p.kennung)/\(p.laeuft ? "anhalten" : "starten")"), kopf: "X-Maschinenraum")
        arbeitet.remove("betrieb:" + p.kennung)
        await holen()
    }

    func schalten(_ a: Webapp, bei p: Steuerprogramm) async {
        guard let o = p.oberflaeche, let url = URL(string: o) else { return }
        arbeitet.insert("app:" + a.kennung)
        await senden(url.appendingPathComponent("api/apps/\(a.kennung)/\(a.an ? "anhalten" : "starten")"), kopf: "X-Stellwerk")
        arbeitet.remove("app:" + a.kennung)
        await holen()
    }

    func oeffnen(_ adresse: String) {
        if let url = URL(string: adresse) { NSWorkspace.shared.open(url) }
    }

    func schalten(_ d: Dienst) async {
        arbeitet.insert(d.kennung)
        var anfrage = URLRequest(url: basis.appendingPathComponent("api/dienste/\(d.kennung)/\(d.laeuft ? "anhalten" : "starten")"))
        anfrage.httpMethod = "POST"
        anfrage.setValue("1", forHTTPHeaderField: "X-Maschinenraum")
        _ = try? await URLSession.shared.data(for: anfrage)
        arbeitet.remove(d.kennung)
        await holen()
    }

    func oeffnen() { NSWorkspace.shared.open(basis) }

}

func farbe(_ zustand: String) -> Color {
    switch zustand {
    case "gestoert": return .red
    case "laeuft": return .green
    case "aus": return .gray.opacity(0.5)
    default: return .orange
    }
}

func gb(_ wert: Double) -> String {
    wert < 1 ? "\(Int((wert * 1024).rounded())) MB" : String(format: "%.1f GB", wert).replacingOccurrences(of: ".", with: ",")
}

struct Ansicht: View {
    @ObservedObject var modell: Modell

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Maschinenraum").font(.headline)
                Spacer()
                if let s = modell.stand { Text(s.rechner).foregroundStyle(.secondary) }
            }
            if !modell.erreichbar {
                Label("Der Maschinenraum antwortet nicht.", systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            if let m = modell.stand?.messwerte {
                VStack(alignment: .leading, spacing: 4) {
                    HStack { Text("Speicher"); Spacer(); Text("\(gb(m.speicher_belegt_gb)) von \(gb(m.speicher_gesamt_gb))").monospacedDigit() }
                    ProgressView(value: min(1, m.speicher_belegt_gb / max(1, m.speicher_gesamt_gb)))
                    if let s = m.swap_belegt_gb, let g = m.swap_gesamt_gb, g > 0 {
                        HStack { Text("Auslagerung"); Spacer(); Text("\(gb(s)) von \(gb(g))").monospacedDigit() }.foregroundStyle(.secondary)
                    }
                }
            }
            Divider()
            Text("KI-Dienste").font(.caption).foregroundStyle(.secondary)
            if let dienste = modell.stand?.dienste, !dienste.isEmpty {
                ForEach(dienste) { d in
                    HStack(spacing: 8) {
                        Circle().fill(d.zustand == "gestoert" ? Color.red : d.laeuft ? Color.green : Color.gray.opacity(0.5)).frame(width: 9, height: 9)
                        Text(d.name).lineLimit(1)
                        Spacer()
                        if d.aktiv { Image(systemName: "gearshape.fill").foregroundStyle(.orange).help("arbeitet gerade") }
                        if let jetzt = d.gb_jetzt { Text(gb(jetzt)).monospacedDigit().foregroundStyle(.secondary).help("Bedarf \(gb(d.bedarf_gb))") }
                        if modell.arbeitet.contains(d.kennung) {
                            ProgressView().controlSize(.small)
                        } else {
                            Toggle("", isOn: Binding(get: { d.laeuft }, set: { _ in Task { await modell.schalten(d) } }))
                                .toggleStyle(.switch).labelsHidden().controlSize(.small)
                        }
                    }
                }
            } else {
                Text("Keine KI-Dienste eingetragen.").foregroundStyle(.secondary)
            }
            if let programme = modell.stand?.betrieb, !programme.isEmpty {
                Divider()
                Text("Betrieb").font(.caption).foregroundStyle(.secondary)
                ForEach(programme) { p in
                    HStack(spacing: 8) {
                        Circle().fill(farbe(p.zustand)).frame(width: 9, height: 9)
                        Text(p.name).lineLimit(1)
                        Spacer()
                        if let o = p.oberflaeche, p.laeuft {
                            Button { modell.oeffnen(o) } label: { Image(systemName: "arrow.up.right.square") }
                                .buttonStyle(.borderless).help("\(p.name) öffnen")
                        }
                        if modell.arbeitet.contains("betrieb:" + p.kennung) {
                            ProgressView().controlSize(.small)
                        } else {
                            Toggle("", isOn: Binding(get: { p.laeuft }, set: { _ in Task { await modell.schalten(p) } }))
                                .toggleStyle(.switch).labelsHidden().controlSize(.small)
                        }
                    }
                    ForEach(modell.webapps[p.kennung] ?? []) { a in
                        HStack(spacing: 8) {
                            Circle().fill(farbe(a.zustand)).frame(width: 7, height: 7)
                            Text(a.name).lineLimit(1)
                            Spacer()
                            if let jetzt = a.gb_jetzt { Text(gb(jetzt)).monospacedDigit().foregroundStyle(.secondary) }
                            if let o = a.oberflaeche, a.zustand == "laeuft" {
                                Button { modell.oeffnen(o) } label: { Image(systemName: "arrow.up.right.square") }
                                    .buttonStyle(.borderless).help("\(a.name) im Browser öffnen")
                            }
                            if modell.arbeitet.contains("app:" + a.kennung) {
                                ProgressView().controlSize(.small)
                            } else {
                                Toggle("", isOn: Binding(get: { a.an }, set: { _ in Task { await modell.schalten(a, bei: p) } }))
                                    .toggleStyle(.switch).labelsHidden().controlSize(.mini)
                            }
                        }.padding(.leading, 17)
                    }
                }
            }
            Divider()
            HStack {
                Button("Oberfläche öffnen") { modell.oeffnen() }
                if let adresse = modell.stand?.leitstelle.adresse {
                    Button("Leitstelle") { modell.oeffnen(adresse) }.help("Leitstelle öffnen: verteilt die Aufträge an die KI")
                }
                Spacer()
                Button("Symbol beenden") { NSApplication.shared.terminate(nil) }
                    .help("Beendet nur dieses Symbol; Maschinenraum, Stellwerk und alle Dienste laufen weiter")
            }
        }
        .padding(14)
        .frame(width: 340)
    }
}

@main
struct MaschinenraumMenue: App {
    @StateObject private var modell = Modell()

    var body: some Scene {
        MenuBarExtra {
            Ansicht(modell: modell)
        } label: {
            let laufen = modell.stand?.dienste.filter { $0.laeuft }.count ?? 0
            Image(systemName: modell.erreichbar ? "gearshape.2" : "gearshape.2.fill")
            if laufen > 0 { Text("\(laufen)") }
        }
        .menuBarExtraStyle(.window)
    }
}
