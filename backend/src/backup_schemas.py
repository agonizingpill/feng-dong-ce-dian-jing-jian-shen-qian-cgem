from pydantic import BaseModel,Field,model_validator


class BackupSelection(BaseModel):
    probe_ids:list[int]=Field(default_factory=list,max_length=12)

    @model_validator(mode='after')
    def unique(self):
        if len(self.probe_ids)!=len(set(self.probe_ids)):raise ValueError('备点不能重复登记')
        return self


class SubstitutionInput(BaseModel):
    from_probe_id:int
    to_probe_id:int

    @model_validator(mode='after')
    def different(self):
        if self.from_probe_id==self.to_probe_id:raise ValueError('替换前后不能是同一测点')
        return self
