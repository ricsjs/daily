"""Desenha o daily.ico (calendário azul com ✓) usado no .exe. Requer Pillow (só no build)."""
from PIL import Image, ImageDraw

N = 256
AZUL, ESCURO = "#2563eb", "#1e40af"

img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 36, 240, 240), radius=36, fill=AZUL)
d.rounded_rectangle((16, 36, 240, 100), radius=36, fill=ESCURO)
d.rectangle((16, 70, 240, 100), fill=ESCURO)
d.rounded_rectangle((64, 8, 88, 60), radius=10, fill=ESCURO)
d.rounded_rectangle((168, 8, 192, 60), radius=10, fill=ESCURO)
d.rounded_rectangle((44, 116, 212, 216), radius=16, fill="white")
d.line([(82, 166), (114, 196), (176, 134)], fill=AZUL, width=22, joint="curve")

img.save("daily.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("daily.ico gerado")
