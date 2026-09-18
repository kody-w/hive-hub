import qrcode from "qrcode-generator";

qrcode.stringToBytes = (value) => [...Buffer.from(value, "utf8")];

export function createQrSvg(value, errorCorrectionLevel = "M") {
  const qr = qrcode(0, errorCorrectionLevel);
  qr.addData(value, "Byte");
  qr.make();
  return `${qr.createSvgTag({
    cellSize: 8,
    margin: 32,
    scalable: true
  })}\n`;
}
