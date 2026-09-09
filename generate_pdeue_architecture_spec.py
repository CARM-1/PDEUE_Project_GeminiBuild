import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (pages 2+)
        if self._pageNumber > 1:
            self.drawString(54, letter[1] - 36, "PDEUE & IFAS SYSTEM ARCHITECTURE SPECIFICATION")
            self.drawRightString(letter[0] - 54, letter[1] - 36, "GOVERNANCE, DESKTOPS & ACCOUNTING")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(54, letter[1] - 42, letter[0] - 54, letter[1] - 42)

        # Footer
        text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 54, 36, text)
        self.drawString(54, 36, "CONFIDENTIAL - PRIVATE LINEAL FAMILY OFFICE USE ONLY (SEC RULE 202(a)(11)(G)-1)")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 48, letter[0] - 54, 48)
        self.restoreState()

def build_pdf(filename="PDEUE_IFAS_System_Architecture_Spec.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    # Custom Typography Palette
    c_primary = colors.HexColor("#0F172A")    # Dark Slate
    c_accent = colors.HexColor("#0284C7")     # Cerulean Teal
    c_subtext = colors.HexColor("#334155")    # Charcoal
    c_border = colors.HexColor("#E2E8F0")     # Light Gray
    c_bg_tile = colors.HexColor("#F8FAFC")    # Off-white / Ice
    c_green = colors.HexColor("#16A34A")      # Emerald
    c_yellow = colors.HexColor("#D97706")     # Amber
    c_red = colors.HexColor("#DC2626")        # Crimson

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=c_primary,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=c_accent,
        spaceAfter=12
    )

    h1_style = ParagraphStyle(
        'Header1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=c_primary,
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=c_subtext,
        spaceAfter=5
    )

    bullet_style = ParagraphStyle(
        'BulletDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=c_subtext,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3
    )

    tile_title = ParagraphStyle(
        'TileTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=c_accent
    )

    tile_body = ParagraphStyle(
        'TileBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10.5,
        textColor=c_subtext
    )

    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white
    )

    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=c_primary
    )

    story = []

    # Title & Metadata Banner
    story.append(Paragraph("PDEUE & IFAS SYSTEM ARCHITECTURE SPECIFICATION", title_style))
    story.append(Paragraph("Reconciled Governance, Role-Based Desktops, Capital Flow & Accounting Boundary | Binding Lexicon v0.4", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_accent, spaceBefore=0, spaceAfter=8))

    # SECTION 1: EXECUTIVE & CHIEF ADMIN COCKPIT
    story.append(Paragraph("1. CHIEF ADMINISTRATOR COCKPIT & GRANULAR ANALYTICS ENGINE", h1_style))
    story.append(Paragraph(
        "The Chief Administrator Workspace (/dashboard) serves as the primary governance center for the Financial Generation System. "
        "It integrates forensic trade drill-down, live order book microstructures, and multi-timeframe capital tracking.", body_style
    ))

    t1 = [
        Paragraph("Granular Contract Drill-Down (IF-015)", tile_title),
        Paragraph("Enables point-in-time forensic inspection. Clicking any active or historical contract slides out a detailed telemetry drawer displaying raw NWP weather ensemble vectors, BLS CPI release components, model probability curves, and VWAP execution timestamps.", tile_body)
    ]
    t2 = [
        Paragraph("Microstructure & Slippage Barrier", tile_title),
        Paragraph("Visualizes resting Central Limit Order Book (CLOB) depth across Kalshi and Polymarket. Tracks dynamic order-book walking and fail-closed aborts whenever market sweeps induce slippage exceeding the immutable 1.5% ceiling.", tile_body)
    ]
    t3 = [
        Paragraph("Multi-Timeframe Compounding Curve", tile_title),
        Paragraph("Interactive equity visualizer aggregating performance across 1M, 1H, 12H, RTH, 24H, 7D, 14D, 1MO, 1Q, and 1Y horizons. Compares uncommitted cash against mark-to-market valuations and realized waterfall compounding.", tile_body)
    ]
    t4 = [
        Paragraph("Componentized Template Library", tile_title),
        Paragraph("Standardized CSS/HTML UI widgets (cards, compounding lines, depth step-charts, and pure-CSS formula tooltips) designed for zero-code reusability across Member and Advisor sub-portals.", tile_body)
    ]

    tile_data = [[t1, t2], [t3, t4]]
    tile_table = Table(tile_data, colWidths=[250, 250])
    tile_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_bg_tile),
        ('BOX', (0,0), (-1,-1), 0.5, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(tile_table)
    story.append(Spacer(1, 8))

    # SECTION 2: MULTI-ROLE DESKTOPS & ONBOARDING
    story.append(Paragraph("2. ROLE-BASED DESKTOP SUITE & ONBOARDING PROVISIONING", h1_style))
    story.append(Paragraph(
        "To maintain least-privilege security and prevent cross-tenant contamination, PDEUE partitions user interfaces into segregated operational domains:", body_style
    ))

    desktop_rows = [
        [
            Paragraph("Portal & Route", table_header),
            Paragraph("Authorized Role", table_header),
            Paragraph("Functional Scope & Feature Surface", table_header),
            Paragraph("Hard Safety Boundaries", table_header)
        ],
        [
            Paragraph("<b>Chief Admin</b><br/>/dashboard", table_cell),
            Paragraph("Chief Administrator / Founder", table_cell),
            Paragraph("Master engine mode toggle, emergency kill switch, dual-control approval queues, CFCP/FAEP meters, member provisioning modal.", table_cell),
            Paragraph("Requires Hardware MFA / WebAuthn. State changes generate structured Action Cards.", table_cell)
        ],
        [
            Paragraph("<b>Member Portal</b><br/>/member", table_cell),
            Paragraph("Lineal Family Members (SCMAs)", table_cell),
            Paragraph("Single-SCMA balance, personal compounding curve, downward-only risk dial (0.5%-5%), autonomous distribution requests, Academy.", table_cell),
            Paragraph("Strictly isolated. Cannot view peer balances, exchange keys, or system-wide risk settings.", table_cell)
        ],
        [
            Paragraph("<b>Advisor Desk</b><br/>/advisor", table_cell),
            Paragraph("Lineal Advisors (Tiers F1-F3)", table_cell),
            Paragraph("Household lineage risk analytics, multi-SCMA exposure aggregation, plain-English decision packet audits, Red-Tier co-signing.", table_cell),
            Paragraph("Read-only / advisory posture. No trade execution, risk dial mutation, or kill-switch controls.", table_cell)
        ],
        [
            Paragraph("<b>System Console</b><br/>/admin/tech", table_cell),
            Paragraph("Technical Operators (T1-T3)", table_cell),
            Paragraph("Daemon polling health, token-bucket rates, container CPU/RAM loads, exchange WebSocket heartbeat diagnostics.", table_cell),
            Paragraph("Redacted financial plane. Cannot view dollar balances, member names, or ledger books.", table_cell)
        ]
    ]

    desk_table = Table(desktop_rows, colWidths=[70, 85, 185, 160])
    desk_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_primary),
        ('BOX', (0,0), (-1,-1), 0.5, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(desk_table)
    story.append(Spacer(1, 8))

    # SECTION 3: FINANCIAL ACCOUNTS & DECENTRALIZED DISTRIBUTIONS
    story.append(Paragraph("3. FINANCIAL ACCOUNTS, CASH FLOWS & DECENTRALIZED DISTRIBUTIONS", h1_style))
    story.append(Paragraph(
        "PDEUE enforces strict legal and structural separation between physical money custody and virtual trading state. "
        "The engine operates as a Financial Generation Engine (FGE) rather than an authoritative bank depository.", body_style
    ))

    story.append(Paragraph("• <b>Master Custodial Account (FBO Entity):</b> Commercial checking or trust account opened under the family investment LLC/Trust 'For Benefit Of' family members. Holds seed principal. PDEUE has zero direct credentials or banking API connections.", bullet_style))
    story.append(Paragraph("• <b>Venue Escrow Collateral:</b> CFTC-regulated USD escrow at Kalshi and USDC smart-contract proxy at Polymarket. Mapped internally as exact integer cents.", bullet_style))
    story.append(Paragraph("• <b>Member Personal Bank Accounts:</b> External retail accounts owned by members. Linked to PDEUE exclusively via non-sensitive reference tokens (e.g., EXT-REF-CHASE-****4812). Real account/routing numbers are never stored in PDEUE.", bullet_style))
    story.append(Paragraph("• <b>Virtual Double-Entry Ledgers (ADR-008):</b> 64-bit integer-cent sub-ledgers partitioning cash across Self-Contained Member Accounts (SCMAs), the 10% Central Familial Common Pool (CFCP), and the 3% Founder Endowment Pool (FAEP).", bullet_style))
    story.append(Paragraph("• <b>Platform Yield Accrual:</b> The PlatformYieldAdapter captures Treasury bill yields paid by venues on unallocated cash, crediting interest back to originating member SCMAs or common reserves.", bullet_style))

    story.append(Spacer(1, 3))
    story.append(Paragraph("<b>Decentralized Member Distribution Gateway:</b>", body_style))

    dist_data = [
        [
            Paragraph("GREEN TIER (Routine Profit)", table_header),
            Paragraph("YELLOW TIER (Buffer Advisory)", table_header),
            Paragraph("RED TIER (Capital Preservation)", table_header)
        ],
        [
            Paragraph("<b>Threshold:</b> Net profit withdrawal leaving original seed and operating buffer intact.<br/><br/><b>Flow:</b> Instant, autonomous execution. No human gatekeepers. Emits signed ADR-009 event directly to IFAS for bank ACH.", table_cell),
            Paragraph("<b>Threshold:</b> Withdrawal dips into operational buffer or reduces compounding velocity.<br/><br/><b>Flow:</b> AI Copilot generates educational impact card. Member reviews velocity trade-off and retains final execution authority.", table_cell),
            Paragraph("<b>Threshold:</b> Requests drawing down seed principal or rapid successive drawdowns.<br/><br/><b>Flow:</b> 24-hour cooling-off period. Requires dual-confirmation from assigned F1/F2 mentors to prevent panic liquidation.", table_cell)
        ]
    ]
    dist_table = Table(dist_data, colWidths=[166, 166, 168])
    dist_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), c_green),
        ('BACKGROUND', (1,0), (1,0), c_yellow),
        ('BACKGROUND', (2,0), (2,0), c_red),
        ('BOX', (0,0), (-1,-1), 0.5, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('BACKGROUND', (0,1), (-1,1), c_bg_tile),
    ]))
    story.append(dist_table)
    story.append(Spacer(1, 8))

    # SECTION 4: LINEAL MENTORSHIP & GOVERNANCE
    story.append(Paragraph("4. LINEAL MENTORSHIP, GOVERNANCE & DELEGATION", h1_style))
    story.append(Paragraph("• <b>F1 / F2 Mentorship Layer:</b> Every junior member is paired with a peer mentor (F1) and household senior lead (F2) to build generational financial literacy. Mentors review progress and co-sign Red-Tier withdrawals without holding trading authority.", bullet_style))
    story.append(Paragraph("• <b>House-Tabulated CFCP Treasury Governance:</b> To prevent large family branches from dominating common treasury allocations, CFCP grant proposals require a bicameral threshold: a member popular vote (>50%) AND a supermajority (>=75%) of recognized Lineal Houses.", bullet_style))
    story.append(Paragraph("• <b>Executive Administrative Delegation:</b> The Chief Administrator delegates technical cloud operations to the CTO (T3) and financial risk bounds to the CRO (F3) via dual-control co-signatures, backed by cryptographic session leases for acting administrators.", bullet_style))
    story.append(Spacer(1, 8))

    # SECTION 5: INDEPENDENT FINANCIAL ACCOUNTING SYSTEM (IFAS)
    story.append(Paragraph("5. INDEPENDENT FINANCIAL ACCOUNTING SYSTEM (IFAS) BOUNDARY", h1_style))
    story.append(Paragraph(
        "IFAS is a physically and logically decoupled general-ledger application operating as an asynchronous consumer of PDEUE event streams. "
        "Development commences following portal template staging and prior to production capital funding.", body_style
    ))
    story.append(Paragraph("• <b>Signed Event Boundary (ADR-009):</b> PDEUE emits immutable, sealed JSON-LD records (BALANCE_SETTLEMENT, WATERFALL_DISTRIBUTION, CAPITAL_SWEEP) signed via HMAC-SHA256. IFAS validates signatures and returns idempotent receipts.", bullet_style))
    story.append(Paragraph("• <b>Zero Depository Credentials in Engine:</b> PDEUE contains zero bank routing or account credentials. All fiat wire and ACH disbursements are managed exclusively inside IFAS behind institutional banking controls.", bullet_style))
    story.append(Paragraph("• <b>Physical & Network Isolation:</b> Hosted in a dedicated VPC at accounting.narratix.io. Communicates with PDEUE via authenticated REST outbox APIs over TLS 1.3 with hardware security key (FIDO2) enforcement.", bullet_style))
    story.append(Spacer(1, 8))

    # SECTION 6: COMMUNICATIONS, ACADEMY & HOSTING TOPOLOGY
    story.append(Paragraph("6. COMMUNICATIONS, EDUCATIONAL ACADEMY & NARRATIX.IO TOPOLOGY", h1_style))
    story.append(Paragraph("• <b>Lineage Community Hub (/community):</b> Isolated family hearth for non-business communications, milestone celebrations, and family news, firewalled completely from trading engine databases.", bullet_style))
    story.append(Paragraph("• <b>Sandboxed Video Conferencing:</b> Jitsi Meet container embedded via an isolated HTML iframe (allow='camera; microphone') on meet.narratix.io with zero access to API tokens or financial state.", bullet_style))
    story.append(Paragraph("• <b>Interactive AI Academy:</b> AICopilotEngine delivers on-the-fly tutoring, explaining binary option geometry, Kelly sizing, and point-in-time trade decisions directly inside the UI.", bullet_style))
    story.append(Paragraph("• <b>Unified narratix.io Subdomain Routing:</b>", body_style))

    sub_rows = [
        [Paragraph("Subdomain", table_header), Paragraph("Target Service", table_header), Paragraph("Access Protocol & Purpose", table_header)],
        [Paragraph("admin.narratix.io", table_cell), Paragraph("Chief Admin Cockpit", table_cell), Paragraph("Hardware MFA / FIDO2. Mode switches, kill switch, dual control.", table_cell)],
        [Paragraph("family.narratix.io", table_cell), Paragraph("Member & Advisor Portals", table_cell), Paragraph("OAuth2. Single-SCMA views, downward risk dials, Academy hub.", table_cell)],
        [Paragraph("pdeue.narratix.io", table_cell), Paragraph("Trading Engine Core", table_cell), Paragraph("API Token / IP Allowlist. Market data ingestion & execution dispatch.", table_cell)],
        [Paragraph("accounting.narratix.io", table_cell), Paragraph("IFAS Gateway", table_cell), Paragraph("Private Cloud / Cloudflare Tunnel. General ledger & tax export.", table_cell)],
    ]
    sub_table = Table(sub_rows, colWidths=[120, 130, 250])
    sub_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_subtext),
        ('BOX', (0,0), (-1,-1), 0.5, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(sub_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[SUCCESS] Architecture specification compiled to: {os.path.abspath(filename)}")

if __name__ == '__main__':
    build_pdf()