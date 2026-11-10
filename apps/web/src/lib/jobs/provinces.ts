// 34 tỉnh/thành từ 01/07/2025, chép từ db/seed/seed_reference_data.sql (ref.provinces).
// Web không đọc được schema `ref` qua PostgREST (chỉ mở `api`), và mã tỉnh không đổi,
// nên giữ bản sao ở đây. Sửa seed thì sửa cả file này.
export type Province = { code: number; name: string };

export const PROVINCES: Province[] = [
  { code: 1, name: "Hà Nội" },
  { code: 4, name: "Cao Bằng" },
  { code: 8, name: "Tuyên Quang" },
  { code: 11, name: "Điện Biên" },
  { code: 12, name: "Lai Châu" },
  { code: 14, name: "Sơn La" },
  { code: 15, name: "Lào Cai" },
  { code: 19, name: "Thái Nguyên" },
  { code: 20, name: "Lạng Sơn" },
  { code: 22, name: "Quảng Ninh" },
  { code: 24, name: "Bắc Ninh" },
  { code: 25, name: "Phú Thọ" },
  { code: 31, name: "Hải Phòng" },
  { code: 33, name: "Hưng Yên" },
  { code: 37, name: "Ninh Bình" },
  { code: 38, name: "Thanh Hóa" },
  { code: 40, name: "Nghệ An" },
  { code: 42, name: "Hà Tĩnh" },
  { code: 44, name: "Quảng Trị" },
  { code: 46, name: "Huế" },
  { code: 48, name: "Đà Nẵng" },
  { code: 51, name: "Quảng Ngãi" },
  { code: 52, name: "Gia Lai" },
  { code: 56, name: "Khánh Hòa" },
  { code: 66, name: "Đắk Lắk" },
  { code: 68, name: "Lâm Đồng" },
  { code: 75, name: "Đồng Nai" },
  { code: 79, name: "TP. Hồ Chí Minh" },
  { code: 80, name: "Tây Ninh" },
  { code: 82, name: "Đồng Tháp" },
  { code: 86, name: "Vĩnh Long" },
  { code: 91, name: "An Giang" },
  { code: 92, name: "Cần Thơ" },
  { code: 96, name: "Cà Mau" },
];

/** Nhiều tin IT nhất: hiện sẵn, các tỉnh khác ẩn sau "Xem tất cả". */
export const POPULAR_PROVINCES = [1, 79, 48];

const BY_CODE = new Map(PROVINCES.map((p) => [p.code, p]));

export function provinceName(code: number): string {
  return BY_CODE.get(code)?.name ?? `Tỉnh ${code}`;
}

export function isProvinceCode(code: number): boolean {
  return BY_CODE.has(code);
}

/** Chữ thường, bỏ dấu, đ → d: để gõ "ho chi minh" vẫn tìm ra "TP. Hồ Chí Minh". */
export function unaccent(s: string): string {
  return s
    .normalize("NFD")
    .replace(/\p{Mn}/gu, "")
    .replace(/đ/gi, "d")
    .toLowerCase()
    .trim();
}
