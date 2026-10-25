from alembic.config import Config
from alembic import command
from app.nexus.seed import seed

if __name__=='__main__':
    command.upgrade(Config('alembic-nexus.ini'),'head')
    seed()
    print('Nexus schema and seed accounts ready')
