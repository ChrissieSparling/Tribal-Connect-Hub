import qrcode

data = "https://github.com/ChrissieSparling/Tribal-Connect-Hub"
img = qrcode.make(data)
img.save("tribalconnect_qr.png")