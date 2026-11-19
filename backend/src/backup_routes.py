from fastapi import APIRouter,Depends
from sqlalchemy import select

from .db import db_session
from .auth import current,writers,admin
from .backup_models import LayoutBackup,LayoutSubstitution
from .backup_schemas import BackupSelection,SubstitutionInput
from . import backup_service as backups
router=APIRouter()


@router.get('/layouts/{layout_id}/backups')
def list_backups(layout_id:int,s=Depends(db_session),u=Depends(current)):
    return backups.backup_views(s,layout_id)


@router.put('/layouts/{layout_id}/backups')
def register_backups(layout_id:int,d:BackupSelection,s=Depends(db_session),u=Depends(writers)):
    x=backups.register(s,layout_id,d.probe_ids,u);s.commit();return x


@router.get('/layout-substitutions')
def list_substitutions(s=Depends(db_session),u=Depends(current)):
    return [backups.view(s,x) for x in s.scalars(select(LayoutSubstitution).order_by(LayoutSubstitution.id.desc()))]


@router.post('/layouts/{layout_id}/substitutions')
def propose_substitution(layout_id:int,d:SubstitutionInput,s=Depends(db_session),u=Depends(writers)):
    x=backups.propose(s,layout_id,d,u);s.commit();return x


@router.post('/layout-substitutions/{id}/sign')
def sign_substitution(id:int,s=Depends(db_session),u=Depends(admin)):
    x=backups.sign(s,id,u);s.commit();return x


@router.post('/layout-substitutions/{id}/withdraw')
def withdraw_substitution(id:int,s=Depends(db_session),u=Depends(admin)):
    x=backups.withdraw(s,id,u);s.commit();return x
