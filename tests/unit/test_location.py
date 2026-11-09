import unicodedata

import pytest

from ingestion.location import (
    LocationResult,
    ProvinceDataError,
    build_index,
    job_location_rows,
    load_index_from_seed,
    normalize_key,
    normalize_location,
    parsed_ratio,
)

HA_NOI, DA_NANG, HUE, TP_HCM, AN_GIANG = 1, 48, 46, 79, 91

# 63 tỉnh/thành trước 01/07/2025, viết theo dạng alias_norm.
OLD_PROVINCES = """
ha noi, ho chi minh, hai phong, da nang, can tho, ha giang, cao bang, bac kan, tuyen quang,
lao cai, dien bien, lai chau, son la, yen bai, hoa binh, thai nguyen, lang son, quang ninh,
bac giang, phu tho, vinh phuc, bac ninh, hai duong, hung yen, thai binh, ha nam, nam dinh,
ninh binh, thanh hoa, nghe an, ha tinh, quang binh, quang tri, thua thien hue, quang nam,
quang ngai, binh dinh, phu yen, khanh hoa, ninh thuan, binh thuan, kon tum, gia lai, dak lak,
dak nong, lam dong, binh phuoc, tay ninh, binh duong, dong nai, ba ria vung tau, long an,
tien giang, ben tre, tra vinh, vinh long, dong thap, an giang, kien giang, hau giang,
soc trang, bac lieu, ca mau
"""


@pytest.fixture(scope="module")
def index():
    return load_index_from_seed()


def test_seed_has_34_new_provinces(index):
    assert len(index.names) == 34
    assert index.names[TP_HCM] == "TP. Hồ Chí Minh"


def test_seed_maps_all_63_old_provinces(index):
    old = [name.strip() for name in OLD_PROVINCES.replace("\n", " ").split(",")]
    assert len(old) == 63
    assert [name for name in old if name not in index.aliases] == []


def test_every_new_province_reachable(index):
    assert set(index.aliases.values()) == set(index.names)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Thanh Hoá", "thanh hoa"),
        ("Đà Nẵng", "da nang"),
        (unicodedata.normalize("NFD", "Hà Nội"), "ha noi"),
        ("TP.HCM", "tp hcm"),
        ("Bà Rịa - Vũng Tàu", "ba ria vung tau"),
    ],
)
def test_normalize_key(text, expected):
    assert normalize_key(text) == expected


@pytest.mark.parametrize(
    ("location", "codes"),
    [
        ("Bình Dương", (TP_HCM,)),  # US-09/AC1
        ("Hồ Chí Minh (mới)", (TP_HCM,)),  # dạng TopCV đang dùng
        ("TP. Hồ Chí Minh", (TP_HCM,)),
        ("TP.HCM", (TP_HCM,)),
        ("Sài Gòn", (TP_HCM,)),
        ("Bà Rịa - Vũng Tàu", (TP_HCM,)),  # không tách theo dấu gạch
        ("Kiên Giang", (AN_GIANG,)),
        ("Thừa Thiên Huế", (HUE,)),
        ("Quảng Nam", (DA_NANG,)),
        (unicodedata.normalize("NFD", "Hà Nội"), (HA_NOI,)),
        ("Hà Nội & Hồ Chí Minh (mới)", (HA_NOI, TP_HCM)),
        ("Hồ Chí Minh, Hà Nội, Hồ Chí Minh", (TP_HCM, HA_NOI)),  # bỏ trùng, giữ thứ tự
        ("Cầu Giấy", (HA_NOI,)),
        ("Quận 7, TP Hồ Chí Minh", (TP_HCM,)),
        ("Hồ Chí Minh - Quận 1", (TP_HCM,)),
        ("TP Vinh", (40,)),  # Nghệ An
        ("Vĩnh Long", (86,)),  # không bị đọc thành "vinh"
    ],
)
def test_province_codes(index, location, codes):
    result = normalize_location(location, index=index)
    assert result.province_codes == codes
    assert result.unmatched == ()


@pytest.mark.parametrize("location", ["Vĩnh Yên", "Nhật Bản", "Toàn quốc"])
def test_unknown_place_is_reported_not_guessed(index, location):
    result = normalize_location(location, index=index)
    assert result.province_codes == ()
    assert result.unmatched == (normalize_key(location),)
    assert not result.is_parsed


@pytest.mark.parametrize(
    ("location", "title", "mode", "codes"),
    [
        ("Hà Nội", "Backend Developer", "onsite", (HA_NOI,)),
        ("Hà Nội", "Java Developer (Hybrid)", "hybrid", (HA_NOI,)),
        ("Remote", "Python Developer", "remote", ()),
        ("Hà Nội, Remote", None, "remote", (HA_NOI,)),
        ("", "Frontend - Làm việc từ xa", "remote", ()),
        ("Hà Nội", "Senior Engineer - Hybrid/Remote", "hybrid", (HA_NOI,)),
        (None, None, "unknown", ()),
    ],
)
def test_work_mode(index, location, title, mode, codes):
    result = normalize_location(location, title, index=index)
    assert result.work_mode == mode
    assert result.province_codes == codes
    assert result.unmatched == ()


def test_remote_counts_as_parsed_for_ac3(index):
    results = [
        normalize_location("Hà Nội", index=index),
        normalize_location("Remote", index=index),
        normalize_location("Nhật Bản", index=index),
        normalize_location("Bình Dương", index=index),
    ]
    assert parsed_ratio(results) == 0.75
    assert parsed_ratio([]) == 0.0


def test_job_location_rows():
    result = LocationResult(province_codes=(HA_NOI, TP_HCM), work_mode="onsite", unmatched=())
    assert job_location_rows(42, result) == [(42, HA_NOI), (42, TP_HCM)]


def test_build_index_rejects_unknown_code():
    with pytest.raises(ProvinceDataError, match="mã tỉnh 99 không tồn tại"):
        build_index({1: "Hà Nội"}, {"hn": 99})


def test_build_index_rejects_alias_with_two_provinces():
    with pytest.raises(ProvinceDataError, match="'dn' trỏ tới cả mã 48 và 75"):
        build_index({48: "Đà Nẵng", 75: "Đồng Nai"}, {"dn": 48, "DN": 75})


def test_seed_without_insert_block_is_rejected(tmp_path):
    seed = tmp_path / "seed.sql"
    seed.write_text("-- trống\n", encoding="utf-8")
    with pytest.raises(ProvinceDataError, match="ref.provinces"):
        load_index_from_seed(seed)
