import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from lunar_python import Lunar, LunarYear

SECTIONS = (
    "overview", "personality", "love", "career", "wealth", "health",
    "family", "children", "move", "friends", "home", "spirit", "parents",
)
Section = Literal["overview", "personality", "love", "career", "wealth", "health", "family", "children", "move", "friends", "home", "spirit", "parents"]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Birth(BaseModel):
    year: int = Field(ge=2000, le=2026)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    hour: int = Field(ge=0, le=11, description="原始命盘的时辰索引；不得自动按钟点换算")
    gender: Literal["male", "female"]

    @field_validator('hour', mode='before')
    @classmethod
    def wrap_twelve(cls, value):
        return 0 if value == 12 else value

    @model_validator(mode="after")
    def valid_date(self):
        date(self.year, self.month, self.day)
        return self

    @property
    def chart_key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}-{self.hour}-{self.gender}"


class BirthLookup(BaseModel):
    location_id: str | None = None
    time_fold: int = Field(default=0, ge=0, le=1)
    name: str = Field(default='', max_length=80)
    clock_hour: int | None = Field(default=None, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    calendar: Literal['solar', 'lunar'] = 'solar'
    year: int = Field(ge=1999, le=2026)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    leap_month: bool = False
    hour: int = Field(default=0, ge=0, le=11)
    gender: Literal['male', 'female']

    @model_validator(mode='after')
    def valid_input(self):
        self.name = self.name.strip()
        if self.clock_hour is not None:
            self.hour = ((self.clock_hour + 1) // 2) % 12
        if self.calendar == 'solar':
            if self.leap_month:
                raise ValueError('公历日期没有闰月')
            date(self.year, self.month, self.day)
        else:
            lunar_year = LunarYear.fromYear(self.year)
            lunar_month = -self.month if self.leap_month else self.month
            days = {item.getMonth(): item.getDayCount() for item in lunar_year.getMonthsInYear()}
            if lunar_month not in days or self.day > days[lunar_month]:
                raise ValueError('农历日期或闰月无效')
        return self

    def to_birth(self) -> Birth:
        if self.calendar == 'lunar':
            solar = Lunar.fromYmd(self.year, -self.month if self.leap_month else self.month, self.day).getSolar()
            year, month, day = solar.getYear(), solar.getMonth(), solar.getDay()
        else:
            year, month, day = self.year, self.month, self.day
        if self.location_id is not None:
            if self.clock_hour is None:
                raise ValueError('出生地校正需要准确的出生小时和分钟')
            from .astrology import correct_time
            corrected = correct_time(year, month, day, self.clock_hour, self.minute, self.location_id, self.time_fold)
            effective = date.fromisoformat(corrected['chart_date'])
            year, month, day = effective.year, effective.month, effective.day
            hour = corrected['branch']
        else:
            hour = self.hour
        if not 2000 <= year <= 2026:
            raise ValueError('当前命盘仅覆盖公历 2000–2026 年')
        return Birth(year=year, month=month, day=day, hour=hour, gender=self.gender)


class SavedBirthLookup(BirthLookup):
    name: str = Field(min_length=1, max_length=80)

    @model_validator(mode='after')
    def named(self):
        if not self.name:
            raise ValueError('请输入姓名')
        return self


class ChartRow(BaseModel):
    k: str
    y: int
    m: int
    d: int
    h: int
    g: Literal["male", "female"]
    ms: str | None = None
    t: dict[str, int] = Field(default_factory=dict)
    c: dict[str, str]

    @model_validator(mode="after")
    def consistent(self):
        birth = Birth(year=self.y, month=self.m, day=self.d, hour=self.h, gender=self.g)
        if self.k != birth.chart_key:
            raise ValueError(f"chart key mismatch: {self.k} != {birth.chart_key}")
        if set(self.c) != set(SECTIONS) or any(not self.c[s] for s in SECTIONS):
            raise ValueError(f"chart {self.k} must contain exactly 13 nonempty sections")
        if self.t and set(self.t) != set(SECTIONS):
            raise ValueError(f"chart {self.k} has incomplete token metadata")
        return self


class TianjiRow(BaseModel):
    book: str
    h2: str
    h3: str | None = None
    quote: str
    section: int | None = None
    t_hms: str | None = None
    note: str | None = None
    bvid: str | None = None
    part: int | None = None

    @property
    def content_hash(self) -> str:
        return digest(json.dumps(self.model_dump(), ensure_ascii=False, sort_keys=True))
