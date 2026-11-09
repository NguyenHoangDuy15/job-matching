-- =====================================================================
--  Intelligent Job Matching — Seed Reference Data (v2.0)
--  Bao gồm:
--    1. 34 Tỉnh/Thành phố trực thuộc TW (Nghị quyết Quốc hội, hiệu lực 01/07/2025)
--    2. Ánh xạ 63 tỉnh/thành cũ + biến thể viết tắt tiếng Việt/Anh → 34 tỉnh/thành mới
--    3. 8 Nhóm nghề IT (Job Families) + 0 = Tất cả
--    4. 7 Danh mục kỹ năng (Skill Categories) + Bộ kỹ năng cốt lõi ban đầu
--    5. 6 Nguồn tuyển dụng trong ops.sources
-- =====================================================================

-- 1. 34 Đơn vị hành chính cấp tỉnh (6 thành phố trực thuộc TW + 28 tỉnh)
insert into ref.provinces (code, name, name_unaccent, kind, region) values
  (1,  'Hà Nội',            'ha noi',            'thanh_pho', 'Đồng bằng sông Hồng'),
  (4,  'Cao Bằng',          'cao bang',          'tinh',      'Trung du và miền núi phía Bắc'),
  (8,  'Tuyên Quang',       'tuyen quang',       'tinh',      'Trung du và miền núi phía Bắc'),
  (11, 'Điện Biên',         'dien bien',         'tinh',      'Trung du và miền núi phía Bắc'),
  (12, 'Lai Châu',          'lai chau',          'tinh',      'Trung du và miền núi phía Bắc'),
  (14, 'Sơn La',            'son la',            'tinh',      'Trung du và miền núi phía Bắc'),
  (15, 'Lào Cai',           'lao cai',           'tinh',      'Trung du và miền núi phía Bắc'),
  (19, 'Thái Nguyên',       'thai nguyen',       'tinh',      'Trung du và miền núi phía Bắc'),
  (20, 'Lạng Sơn',          'lang son',          'tinh',      'Trung du và miền núi phía Bắc'),
  (22, 'Quảng Ninh',        'quang ninh',        'tinh',      'Đồng bằng sông Hồng'),
  (24, 'Bắc Ninh',          'bac ninh',          'tinh',      'Đồng bằng sông Hồng'),
  (25, 'Phú Thọ',           'phu tho',           'tinh',      'Trung du và miền núi phía Bắc'),
  (31, 'Hải Phòng',         'hai phong',         'thanh_pho', 'Đồng bằng sông Hồng'),
  (33, 'Hưng Yên',          'hung yen',          'tinh',      'Đồng bằng sông Hồng'),
  (37, 'Ninh Bình',         'ninh binh',         'tinh',      'Đồng bằng sông Hồng'),
  (38, 'Thanh Hóa',         'thanh hoa',         'tinh',      'Bắc Trung Bộ'),
  (40, 'Nghệ An',           'nghe an',           'tinh',      'Bắc Trung Bộ'),
  (42, 'Hà Tĩnh',           'ha tinh',           'tinh',      'Bắc Trung Bộ'),
  (44, 'Quảng Trị',         'quang tri',         'tinh',      'Bắc Trung Bộ'),
  (46, 'Huế',               'hue',               'thanh_pho', 'Bắc Trung Bộ'),
  (48, 'Đà Nẵng',           'da nang',           'thanh_pho', 'Duyên hải Nam Trung Bộ'),
  (51, 'Quảng Ngãi',        'quang ngai',        'tinh',      'Duyên hải Nam Trung Bộ'),
  (52, 'Gia Lai',           'gia lai',           'tinh',      'Tây Nguyên'),
  (56, 'Khánh Hòa',         'khanh hoa',         'tinh',      'Duyên hải Nam Trung Bộ'),
  (66, 'Đắk Lắk',           'dak lak',           'tinh',      'Tây Nguyên'),
  (68, 'Lâm Đồng',          'lam dong',          'tinh',      'Tây Nguyên'),
  (75, 'Đồng Nai',          'dong nai',          'tinh',      'Đông Nam Bộ'),
  (79, 'TP. Hồ Chí Minh',   'tp ho chi minh',    'thanh_pho', 'Đông Nam Bộ'),
  (80, 'Tây Ninh',          'tay ninh',          'tinh',      'Đông Nam Bộ'),
  (82, 'Đồng Tháp',         'dong thap',         'tinh',      'Đồng bằng sông Cửu Long'),
  (86, 'Vĩnh Long',         'vinh long',         'tinh',      'Đồng bằng sông Cửu Long'),
  (91, 'An Giang',          'an giang',          'tinh',      'Đồng bằng sông Cửu Long'),
  (92, 'Cần Thơ',           'can tho',           'thanh_pho', 'Đồng bằng sông Cửu Long'),
  (96, 'Cà Mau',            'ca mau',            'tinh',      'Đồng bằng sông Cửu Long')
on conflict (code) do update
  set name = excluded.name, name_unaccent = excluded.name_unaccent, kind = excluded.kind, region = excluded.region;

-- 2. Ánh xạ 63 tỉnh/thành cũ + biến thể viết tắt sang 34 tỉnh/thành mới
insert into ref.province_legacy (alias_norm, province_code) values
  -- Hà Nội
  ('ha noi', 1), ('hanoi', 1), ('hn', 1), ('tp ha noi', 1), ('ha tay', 1),
  -- TP. Hồ Chí Minh (gồm TP.HCM + Bình Dương + Bà Rịa - Vũng Tàu)
  ('tp ho chi minh', 79), ('ho chi minh', 79), ('ho chi minh city', 79), ('hcmc', 79), ('hcm', 79), ('sai gon', 79), ('saigon', 79), ('tphcm', 79),
  ('binh duong', 79), ('ba ria vung tau', 79), ('ba ria - vung tau', 79), ('vung tau', 79), ('brvt', 79),
  -- Đà Nẵng (gồm Đà Nẵng + Quảng Nam)
  ('da nang', 48), ('danang', 48), ('dn', 48), ('tp da nang', 48), ('quang nam', 48),
  -- Hải Phòng (gồm Hải Phòng + Hải Dương)
  ('hai phong', 31), ('haiphong', 31), ('hp', 31), ('hai duong', 31),
  -- Cần Thơ (gồm Cần Thơ + Sóc Trăng + Hậu Giang)
  ('can tho', 92), ('cantho', 92), ('soc trang', 92), ('hau giang', 92),
  -- Huế (Thừa Thiên Huế)
  ('hue', 46), ('tp hue', 46), ('thua thien hue', 46), ('thua thien - hue', 46),
  -- Các tỉnh sáp nhập khác (63 → 34)
  ('tuyen quang', 8), ('ha giang', 8),
  ('lao cai', 15), ('yen bai', 15),
  ('thai nguyen', 19), ('bac kan', 19), ('bac can', 19),
  ('phu tho', 25), ('vinh phuc', 25), ('hoa binh', 25),
  ('bac ninh', 24), ('bac giang', 24),
  ('hung yen', 33), ('thai binh', 33),
  ('ninh binh', 37), ('ha nam', 37), ('nam dinh', 37),
  ('quang tri', 44), ('quang binh', 44),
  ('quang ngai', 51), ('kon tum', 51),
  ('gia lai', 52), ('binh dinh', 52), ('quy nhon', 52),
  ('khanh hoa', 56), ('nha trang', 56), ('ninh thuan', 56),
  ('lam dong', 68), ('da lat', 68), ('dak nong', 68), ('binh thuan', 68),
  ('dak lak', 66), ('dac lac', 66), ('buon ma thuot', 66), ('phu yen', 66),
  ('dong nai', 75), ('bien hoa', 75), ('binh phuoc', 75),
  ('tay ninh', 80), ('long an', 80),
  ('dong thap', 82), ('tien giang', 82), ('my tho', 82),
  ('vinh long', 86), ('ben tre', 86), ('tra vinh', 86),
  ('an giang', 91), ('kien giang', 91), ('phu quoc', 91), ('rach gia', 91),
  ('ca mau', 96), ('bac lieu', 96),
  -- Các tỉnh giữ nguyên
  ('cao bang', 4), ('dien bien', 11), ('lai chau', 12), ('son la', 14),
  ('lang son', 20), ('quang ninh', 22), ('ha long', 22),
  ('thanh hoa', 38), ('nghe an', 40), ('vinh', 40), ('ha tinh', 42)
on conflict (alias_norm) do update set province_code = excluded.province_code;

-- 3. Nhóm nghề IT (Job Families)
insert into ref.job_families (id, name) values
  (0, 'Tất cả'),
  (1, 'Backend'),
  (2, 'Frontend'),
  (3, 'Fullstack'),
  (4, 'Mobile'),
  (5, 'Data & AI'),
  (6, 'DevOps & Cloud'),
  (7, 'QA / Tester'),
  (8, 'Product / BA / Khác')
on conflict (id) do update set name = excluded.name;

-- 4. Danh mục kỹ năng (Skill Categories)
insert into ref.skill_categories (id, name) values
  (1, 'Programming Language'),
  (2, 'Backend & Framework'),
  (3, 'Frontend & Mobile'),
  (4, 'Database & Storage'),
  (5, 'Data Engineering & AI/ML'),
  (6, 'DevOps, Cloud & Infra'),
  (7, 'Testing, Security & Process')
on conflict (id) do update set name = excluded.name;

-- 5. Nguồn dữ liệu trong ops.sources
insert into ops.sources (id, code, name, base_url, method, rate_limit_ms, is_enabled, hourly_enabled, tos_note) values
  (1, 'vietnamworks', 'VietnamWorks', 'https://www.vietnamworks.com', 'jsonld',  2000, true,  true,  'Nguồn chính: JSON-LD JobPosting + API listing IT'),
  (2, 'itviec',       'ITviec',       'https://itviec.com',           'html',    2000, true,  false, 'Nguồn chính: chuyên việc làm IT, không đăng nhập lấy lương'),
  (3, 'careerviet',   'CareerViet',   'https://careerviet.vn',        'jsonld',  2000, true,  false, 'Nguồn bổ sung: trang chi tiết có JobPosting + validThrough'),
  (4, 'topcv',        'TopCV',        'https://www.topcv.vn',         'dataset', 2000, false, false, 'Có Cloudflare challenge: dùng dataset VietJobs/Kaggle khi bị chặn'),
  (5, 'jobsgo',       'JobsGO',       'https://jobsgo.vn',            'jsonld',  2000, false, false, 'Nguồn bổ sung sau khi kiểm tra Source Decision Record'),
  (6, 'joboko',       'Joboko',       'https://vn.joboko.com',        'html',    2000, false, false, 'Nguồn bổ sung sau khi kiểm tra Source Decision Record')
on conflict (id) do update
  set code = excluded.code, name = excluded.name, base_url = excluded.base_url,
      method = excluded.method, rate_limit_ms = excluded.rate_limit_ms, tos_note = excluded.tos_note;

