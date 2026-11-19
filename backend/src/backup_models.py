from sqlalchemy import String,Integer,Float,Boolean,ForeignKey,JSON,UniqueConstraint,CheckConstraint,Text
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base


class LayoutBackup(Base):
    """备点随布置一起审签；signed 仅在负责人审签布置时置位。"""
    __tablename__='layout_backups'
    __table_args__=(UniqueConstraint('layout_id','probe_id'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    layout_id:Mapped[int]=mapped_column(ForeignKey('layouts.id'))
    probe_id:Mapped[int]=mapped_column(ForeignKey('probes.id'))
    signed:Mapped[bool]=mapped_column(Boolean,default=False)


class LayoutSubstitution(Base):
    """一次只替换一个主测点，通道数不变；留出集沿用原审签证据。"""
    __tablename__='layout_substitutions'
    __table_args__=(CheckConstraint("state in ('proposed','signed','withdrawn')"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    layout_id:Mapped[int]=mapped_column(ForeignKey('layouts.id'))
    from_probe_id:Mapped[int]=mapped_column(ForeignKey('probes.id'))
    to_probe_id:Mapped[int]=mapped_column(ForeignKey('probes.id'))
    state:Mapped[str]=mapped_column(String(20),default='proposed')
    train_rows:Mapped[int]=mapped_column(Integer,default=0)
    holdout_rows:Mapped[int]=mapped_column(Integer,default=0)
    holdout_mae_n:Mapped[float]=mapped_column(Float,default=0)
    error_limit_n:Mapped[float]=mapped_column(Float,default=0)
    passed:Mapped[bool]=mapped_column(Boolean,default=False)
    evidence:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    created_by:Mapped[str|None]=mapped_column(String(100),nullable=True)
    created_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    signed_by:Mapped[str|None]=mapped_column(String(100),nullable=True)
    signed_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    note:Mapped[str]=mapped_column(Text,default='')
