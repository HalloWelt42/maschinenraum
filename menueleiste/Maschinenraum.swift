// Menüleistensymbol des Maschinenraums: Schnellzugriff auf die Dienste dieses Rechners.
// Holt den Stand von der lokalen Schnittstelle (Port aus Info.plist), schaltet Dienste und öffnet die Oberfläche.
// Es verwaltet selbst nichts; die Wahrheit liegt im Maschinenraum.

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
    let gb: Double
    let gemessen: Bool
    var id: String { kennung }
    var laeuft: Bool { zustand == "laeuft" || zustand == "startet" || zustand == "stoppt" }
}

struct Leitstelle: Decodable { let zustand: String }

struct Stand: Decodable {
    let rechner: String
    let messwerte: Messwerte?
    let dienste: [Dienst]
    let leitstelle: Leitstelle
}

@MainActor
final class Modell: ObservableObject {
    @Published var stand: Stand?
    @Published var erreichbar = true
    @Published var arbeitet: Set<String> = []
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
            if let dienste = modell.stand?.dienste, !dienste.isEmpty {
                ForEach(dienste) { d in
                    HStack(spacing: 8) {
                        Circle().fill(d.zustand == "gestoert" ? Color.red : d.laeuft ? Color.green : Color.gray.opacity(0.5)).frame(width: 9, height: 9)
                        Text(d.name).lineLimit(1)
                        Spacer()
                        if d.gemessen { Text(gb(d.gb)).monospacedDigit().foregroundStyle(.secondary) }
                        if modell.arbeitet.contains(d.kennung) {
                            ProgressView().controlSize(.small)
                        } else {
                            Toggle("", isOn: Binding(get: { d.laeuft }, set: { _ in Task { await modell.schalten(d) } }))
                                .toggleStyle(.switch).labelsHidden().controlSize(.small)
                        }
                    }
                }
            } else {
                Text("Keine Dienste eingetragen.").foregroundStyle(.secondary)
            }
            Divider()
            HStack {
                Button("Oberfläche öffnen") { modell.oeffnen() }
                Spacer()
                Button("Symbol beenden") { NSApplication.shared.terminate(nil) }
                    .help("Beendet nur dieses Symbol; der Maschinenraum und seine Dienste laufen weiter")
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
