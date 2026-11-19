import os
ROLES=('admin','engineer','viewer')
ZONES=('root','mid','tip')
LAYOUT_STATES=('calculating','ready','signed','invalidated','failed')

CERTIFICATE_STATES=('draft','issued')
RUN_STATES=('planned','running','completed')

MOUNT_STATES=('draft','accepted')
BATCH_STATES=('collecting','frozen')
DELIVERY_STATES=('submitted','approved','acknowledged')

SUBSTITUTION_STATES=('proposed','signed','withdrawn')
# 替换组合沿用原审签布置的训练/留出记录；留出 MAE 不得高于原组合的该倍数才准签。
SUBSTITUTION_ERROR_FACTOR=float(os.getenv('SUBSTITUTION_ERROR_FACTOR','1.5'))
# 验证替换组合需要原布置的训练记录与留出记录。
SUBSTITUTION_TRAIN_MIN=2
