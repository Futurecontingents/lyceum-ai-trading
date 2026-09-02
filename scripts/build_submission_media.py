#!/usr/bin/env python3
"""Build Lyceum's judge-facing PDF deck, cover, and silent MP4."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1920
HEIGHT = 1080
BG = "#050811"
INK = "#F4F7FF"
MUTED = "#A5B4D4"
CYAN = "#67E8F9"
VIOLET = "#A78BFA"
GREEN = "#6EE7B7"
RED = "#FB7185"
AMBER = "#FCD34D"
LINE = "#273552"
FONT_PATH = "/System/Library/Fonts/Avenir Next.ttc"


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size=size)


def text_width(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont) -> float:
    return draw.textbbox((0, 0), text, font=face)[2]


def wrap(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or text_width(draw, candidate, face) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def paragraph(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    size: int = 34,
    color: str = INK,
    width: int = 760,
    spacing: int = 16,
) -> int:
    face = font(size)
    x, y = xy
    for line in wrap(draw, text, face, width):
        draw.text((x, y), line, font=face, fill=color)
        y += size + spacing
    return y


def background() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        mix = y / HEIGHT
        color = (5 + int(6 * (1 - mix)), 8 + int(9 * (1 - mix)), 17 + int(25 * (1 - mix)))
        draw.line((0, y, WIDTH, y), fill=color)
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-430, -540, 820, 710), fill=(67, 56, 202, 55))
    glow_draw.ellipse((1410, 630, 2220, 1420), fill=(14, 116, 144, 40))
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")
    return image, ImageDraw.Draw(image)


def chrome(draw: ImageDraw.ImageDraw, number: int, kicker: str, title: str) -> None:
    draw.text((96, 70), kicker.upper(), font=font(21), fill=CYAN)
    draw.text((96, 112), title, font=font(66), fill=INK)
    draw.line((96, 205, 1824, 205), fill=LINE, width=2)
    draw.text((96, 1025), "LYCEUM · PAPER ONLY · NO PROFITABILITY CLAIM", font=font(18), fill=MUTED)
    draw.text((1782, 1025), f"{number:02d}", font=font(18), fill=MUTED)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str = CYAN) -> None:
    draw.line((*start, *end), fill=color, width=5)
    x, y = end
    draw.polygon([(x, y), (x - 18, y - 11), (x - 18, y + 11)], fill=color)


def metric(draw: ImageDraw.ImageDraw, x: int, y: int, value: str, label: str, color: str = CYAN) -> None:
    draw.text((x, y), value, font=font(62), fill=color)
    paragraph(draw, (x, y + 75), label, size=24, color=MUTED, width=480, spacing=8)


def slide_title() -> Image.Image:
    image, draw = background()
    draw.text((96, 78), "LYCEUM", font=font(28), fill=CYAN)
    draw.text((96, 260), "A market of\nAI minds", font=font(112), fill=INK, spacing=10)
    draw.text((102, 535), "Multiple minds. One market.", font=font(42), fill=MUTED)
    draw.text((102, 600), "Lyceum trades the uncertainty.", font=font(42), fill=CYAN)
    draw.line((101, 704, 1100, 704), fill=LINE, width=3)
    draw.text((102, 755), "AI proposes. Math validates. Alpaca executes.", font=font(36), fill=INK)
    draw.text((102, 842), "Autonomous · cost-aware · deterministic risk · Alpaca paper only", font=font(25), fill=MUTED)
    draw.rounded_rectangle((1420, 292, 1720, 592), radius=150, outline=VIOLET, width=8)
    draw.ellipse((1483, 355, 1657, 529), outline=CYAN, width=6)
    draw.ellipse((1537, 409, 1603, 475), fill=GREEN)
    return image


def slide_problem() -> Image.Image:
    image, draw = background()
    chrome(draw, 2, "The problem", "A signal is not an option trade")
    draw.text((116, 290), "Most AI systems stop here", font=font(31), fill=MUTED)
    draw.text((116, 355), "BUY / SELL", font=font(80), fill=VIOLET)
    draw.line((116, 470, 730, 470), fill=LINE, width=3)
    paragraph(draw, (116, 525), "Opaque direction hides confidence, uncertainty, liquidity, maximum loss, and the cost of two crossings.", size=32, color=INK, width=650)
    arrow(draw, (835, 520), (1065, 520))
    draw.text((1110, 290), "Options require the full equation", font=font(31), fill=MUTED)
    for index, line in enumerate(("Expected gross move", "− entry crossing", "− expected exit crossing", "− slippage + risk buffer")):
        draw.text((1110, 365 + index * 72), line, font=font(36), fill=CYAN if index == 0 else INK)
    draw.line((1110, 664, 1725, 664), fill=LINE, width=3)
    draw.text((1110, 700), "> 0  /  TRADE", font=font(39), fill=GREEN)
    draw.text((1110, 770), "<= 0  /  NO_TRADE", font=font(39), fill=RED)
    return image


def slide_architecture() -> Image.Image:
    image, draw = background()
    chrome(draw, 3, "Autonomous backend", "AI can propose. Deterministic code can refuse.")
    rows = [
        (["Alpaca data", "Five beliefs", "Entropy + JSD"], CYAN),
        (["Quant signal", "Defined-risk option", "Execution cost"], VIOLET),
        (["Skeptic", "Risk gate", "Alpaca PAPER", "Journal"], GREEN),
    ]
    y_positions = [315, 545, 775]
    for (labels, color), y in zip(rows, y_positions, strict=True):
        count = len(labels)
        gap = 55
        node_width = (1660 - gap * (count - 1)) // count
        for index, label in enumerate(labels):
            x = 130 + index * (node_width + gap)
            draw.rounded_rectangle((x, y, x + node_width, y + 112), radius=20, outline=color, width=4)
            box = draw.textbbox((0, 0), label, font=font(27))
            draw.text((x + (node_width - (box[2] - box[0])) / 2, y + 37), label, font=font(27), fill=INK)
            if index < count - 1:
                arrow(draw, (x + node_width + 10, y + 56), (x + node_width + gap - 10, y + 56), color)
        if y != y_positions[-1]:
            draw.line((960, y + 112, 960, y + 200), fill=LINE, width=4)
            draw.polygon([(960, y + 208), (949, y + 190), (971, y + 190)], fill=LINE)
    draw.text((134, 940), "Missing required features: INVALID · Economics below hurdle: NO_TRADE", font=font(25), fill=AMBER)
    return image


def slide_agents() -> Image.Image:
    image, draw = background()
    chrome(draw, 4, "The five market minds", "Competing probability distributions—not votes")
    agents = [
        ("Technical", "deterministic", CYAN, [8, 16, 42, 28, 6]),
        ("Options", "deterministic", CYAN, [4, 20, 46, 25, 5]),
        ("News", "Qwen / fallback", VIOLET, [7, 22, 45, 21, 5]),
        ("Bull", "Qwen / fallback", GREEN, [2, 8, 26, 47, 17]),
        ("Bear", "Qwen / fallback", RED, [15, 43, 31, 9, 2]),
    ]
    x0 = 105
    column = 342
    for index, (name, implementation, color, values) in enumerate(agents):
        x = x0 + index * column
        draw.ellipse((x + 88, 286, x + 196, 394), outline=color, width=6)
        draw.text((x + 24, 430), name, font=font(33), fill=INK)
        draw.text((x + 24, 476), implementation, font=font(20), fill=MUTED)
        for bar_index, value in enumerate(values):
            y = 558 + bar_index * 61
            draw.rectangle((x + 24, y, x + 286, y + 18), fill="#17213A")
            draw.rectangle((x + 24, y, x + 24 + int(2.62 * value), y + 18), fill=color)
            draw.text((x + 295, y - 6), f"{value}%", font=font(16), fill=MUTED)
    draw.text((110, 906), "Consensus measures entropy and Jensen–Shannon disagreement. Model text never bypasses schema validation or deterministic fallback.", font=font(24), fill=MUTED)
    return image


def slide_research() -> Image.Image:
    image, draw = background()
    chrome(draw, 5, "Research depth", "Long history, recent intraday detail, real option quotes")
    metric(draw, 112, 300, "33.58 years", "SPY history · 8,453 sessions")
    metric(draw, 720, 300, "56.65 years", "S&P 500 proxy · regime context only", VIOLET)
    metric(draw, 1328, 300, "19", "registered long-history hypotheses", GREEN)
    draw.line((110, 548, 1810, 548), fill=LINE, width=3)
    metric(draw, 112, 630, "361,439", "five-minute observations · 666 sessions")
    metric(draw, 720, 630, "9,627", "point-in-time option structures", VIOLET)
    metric(draw, 1328, 630, "4 layers", "history · intraday · options · forward", GREEN)
    draw.text((112, 930), "Chronological splits · sealed holdout · block bootstrap · surrogate nulls · drop-one-era · quoted-side costs", font=font(25), fill=MUTED)
    return image


def slide_evidence() -> Image.Image:
    image, draw = background()
    chrome(draw, 6, "What survived", "Forecasting evidence ≠ executable alpha")
    columns: list[tuple[str, str, list[str]]] = [
        ("SUPPORTED", GREEN, ["SPY close-to-open drift", "HAR-style volatility forecast", "Execution cost as a first-class target"]),
        ("INCONCLUSIVE", AMBER, ["Full LLM council value-add", "Rare capitulation states", "Volatility monetization"]),
        ("REJECTED", RED, ["Ordinary directional option conversion", "Midpoint P&L as performance", "Proven profitable option edge"]),
    ]
    for index, (label, color, bullets) in enumerate(columns):
        x = 100 + index * 598
        draw.text((x, 300), label, font=font(34), fill=color)
        draw.line((x, 354, x + 500, 354), fill=color, width=5)
        y = 420
        for bullet in bullets:
            draw.ellipse((x, y + 12, x + 13, y + 25), fill=color)
            y = paragraph(draw, (x + 32, y), bullet, size=29, color=INK, width=470, spacing=12) + 34
        if index < 2:
            draw.line((x + 548, 294, x + 548, 875), fill=LINE, width=2)
    draw.text((100, 928), "No promoted strategy. CASH / NO_TRADE remains the defensible baseline.", font=font(30), fill=CYAN)
    return image


def slide_cost() -> Image.Image:
    image, draw = background()
    chrome(draw, 7, "The economic discovery", "The best underlying signal was ~10× too small")
    draw.text((110, 295), "Recent expected SPY move", font=font(30), fill=MUTED)
    draw.rounded_rectangle((110, 355, 249, 445), radius=12, fill=CYAN)
    draw.text((278, 359), "$0.44", font=font(56), fill=CYAN)
    draw.text((110, 535), "Median observed delta-adjusted option hurdle", font=font(30), fill=MUTED)
    draw.rounded_rectangle((110, 595, 1510, 685), radius=12, fill=VIOLET)
    draw.text((1540, 599), "$4.44", font=font(56), fill=VIOLET)
    draw.text((110, 770), "MOVE / COST = 0.098", font=font(44), fill=RED)
    draw.text((110, 852), "0 of 4,878 directional structures cleared estimated quoted crossing.", font=font(31), fill=INK)
    draw.text((110, 920), "A positive midpoint is not an executable fill.", font=font(27), fill=MUTED)
    return image


def slide_failure() -> Image.Image:
    image, draw = background()
    chrome(draw, 8, "Integrity over optics", "Lyceum invalidated its own forward test")
    draw.text((110, 282), "SEP-01 · INVALID", font=font(35), fill=RED)
    left = ["Council producer never ran", "Missing disagreement: silent zero", "C / D lacked frozen inputs", "<60m excursions used future data"]
    y = 350
    for item in left:
        draw.line((110, y + 16, 136, y + 16), fill=RED, width=5)
        draw.text((155, y), item, font=font(29), fill=INK)
        y += 82
    arrow(draw, (840, 530), (1060, 530), AMBER)
    draw.text((1090, 282), "REPAIRED V2 · FAIL CLOSED", font=font(35), fill=GREEN)
    right = ["Five-agent provenance required", "Missing / non-finite: INVALID", "Causal timestamps enforced", "Each horizon scored inside its window"]
    y = 350
    for item in right:
        draw.line((1090, y + 16, 1116, y + 16), fill=GREEN, width=5)
        draw.text((1135, y), item, font=font(29), fill=INK)
        y += 82
    draw.line((110, 735, 1810, 735), fill=LINE, width=3)
    draw.text((110, 795), "The original run is preserved. Reconstruction is POST-HOC ONLY.", font=font(32), fill=AMBER)
    draw.text((110, 865), "Sep-03 is separately frozen, observation-only, and prohibits orders.", font=font(30), fill=MUTED)
    return image


def slide_close() -> Image.Image:
    image, draw = background()
    draw.text((96, 82), "LYCEUM", font=font(28), fill=CYAN)
    draw.text((96, 255), "The system did not\nmanufacture an edge.", font=font(89), fill=INK, spacing=12)
    draw.text((100, 510), "It found what survived, exposed what failed,", font=font(39), fill=MUTED)
    draw.text((100, 570), "and refused trades whose economics did not clear.", font=font(39), fill=MUTED)
    draw.line((100, 684, 1780, 684), fill=LINE, width=3)
    draw.text((100, 745), "AI proposes.", font=font(45), fill=VIOLET)
    draw.text((570, 745), "Math validates.", font=font(45), fill=CYAN)
    draw.text((1095, 745), "Alpaca executes.", font=font(45), fill=GREEN)
    draw.text((100, 855), "Autonomous · auditable · cost-aware · paper only", font=font(30), fill=INK)
    draw.text((100, 924), "Final conclusion: no profitable executable option edge has been demonstrated.", font=font(25), fill=MUTED)
    return image


def build_slides() -> list[Image.Image]:
    return [
        slide_title(),
        slide_problem(),
        slide_architecture(),
        slide_agents(),
        slide_research(),
        slide_evidence(),
        slide_cost(),
        slide_failure(),
        slide_close(),
    ]


def write_video(frame_paths: list[Path], output: Path, ffmpeg: str) -> None:
    duration = 6.5
    transition = 0.4
    command = [ffmpeg, "-y"]
    for frame in frame_paths:
        command.extend(["-loop", "1", "-t", str(duration), "-i", str(frame)])
    filters = [f"[{index}:v]format=yuv420p,setsar=1[v{index}]" for index in range(len(frame_paths))]
    previous = "v0"
    for index in range(1, len(frame_paths)):
        output_label = f"x{index}"
        offset = index * (duration - transition)
        filters.append(
            f"[{previous}][v{index}]xfade=transition=fade:duration={transition}:offset={offset:.1f}[{output_label}]"
        )
        previous = output_label
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{previous}]",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    subprocess.run(command, check=True, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/submission"))
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    slides = build_slides()
    frame_dir = args.output_dir / "slides"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []
    for index, slide in enumerate(slides, start=1):
        frame = frame_dir / f"slide-{index:02d}.png"
        slide.save(frame, format="PNG", optimize=True)
        frame_paths.append(frame)

    slides[0].save(args.output_dir / "lyceum_cover.png", format="PNG", optimize=True)
    slides[0].save(
        args.output_dir / "lyceum_presentation.pdf",
        format="PDF",
        save_all=True,
        append_images=slides[1:],
        resolution=144,
        title="Lyceum — A Market of AI Minds",
        author="Lyceum",
        subject="Hackathon final presentation",
    )
    write_video(frame_paths, args.output_dir / "lyceum_pitch_video.mp4", args.ffmpeg)


if __name__ == "__main__":
    main()
