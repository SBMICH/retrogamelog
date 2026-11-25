"""esquema inicial

Revision ID: 0001
Revises: 
Create Date: 2026-11-25 16:48:49.184628
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('device_models',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('brand', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_device_models')),
    sa.UniqueConstraint('brand', 'name', name=op.f('uq_device_models_brand'))
    )
    op.create_table('emulators',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_emulators')),
    sa.UniqueConstraint('name', name=op.f('uq_emulators_name'))
    )
    op.create_table('genres',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_genres')),
    sa.UniqueConstraint('name', name=op.f('uq_genres_name'))
    )
    op.create_table('platforms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('short_name', sa.String(length=20), nullable=True),
    sa.Column('manufacturer', sa.String(length=50), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=True),
    sa.Column('external_id', sa.String(length=50), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_platforms')),
    sa.UniqueConstraint('source', 'external_id', name=op.f('uq_platforms_source'))
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('username', sa.String(length=30), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_public', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index('uq_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=True)
    op.create_index('uq_users_username_lower', 'users', [sa.literal_column('lower(username)')], unique=True)
    op.create_table('devices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('device_model_id', sa.Integer(), nullable=False),
    sa.Column('nickname', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['device_model_id'], ['device_models.id'], name=op.f('fk_devices_device_model_id_device_models')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_devices_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_devices'))
    )
    op.create_table('games',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('platform_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('release_year', sa.SmallInteger(), nullable=True),
    sa.Column('developer', sa.String(length=150), nullable=True),
    sa.Column('icon_url', sa.String(length=500), nullable=True),
    sa.Column('cover_url', sa.String(length=500), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=True),
    sa.Column('external_id', sa.String(length=50), nullable=True),
    sa.Column('details_fetched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['platform_id'], ['platforms.id'], name=op.f('fk_games_platform_id_platforms')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_games')),
    sa.UniqueConstraint('source', 'external_id', name=op.f('uq_games_source'))
    )
    op.create_index(op.f('ix_games_title'), 'games', ['title'], unique=False)
    op.create_table('game_genres',
    sa.Column('game_id', sa.Integer(), nullable=False),
    sa.Column('genre_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['game_id'], ['games.id'], name=op.f('fk_game_genres_game_id_games'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['genre_id'], ['genres.id'], name=op.f('fk_game_genres_genre_id_genres'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('game_id', 'genre_id', name=op.f('pk_game_genres'))
    )
    op.create_table('user_games',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('playing', 'backlog', 'completed', 'dropped', name='game_status'), nullable=False),
    sa.Column('rating', sa.SmallInteger(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('priority', sa.SmallInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('priority BETWEEN 1 AND 3', name=op.f('ck_user_games_priority_range')),
    sa.CheckConstraint('rating BETWEEN 1 AND 10', name=op.f('ck_user_games_rating_range')),
    sa.ForeignKeyConstraint(['game_id'], ['games.id'], name=op.f('fk_user_games_game_id_games')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_games_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_games')),
    sa.UniqueConstraint('user_id', 'game_id', name=op.f('uq_user_games_user_id'))
    )
    op.create_table('log_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_game_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('started', 'completed', 'dropped', 'replayed', 'note', name='log_kind'), nullable=False),
    sa.Column('entry_date', sa.Date(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_game_id'], ['user_games.id'], name=op.f('fk_log_entries_user_game_id_user_games'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_log_entries'))
    )
    op.create_table('play_setups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_game_id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('emulator_id', sa.Integer(), nullable=True),
    sa.Column('performance', sa.Enum('perfect', 'playable', 'issues', 'unplayable', name='performance'), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], name=op.f('fk_play_setups_device_id_devices'), deferrable=True, initially='DEFERRED'),
    sa.ForeignKeyConstraint(['emulator_id'], ['emulators.id'], name=op.f('fk_play_setups_emulator_id_emulators')),
    sa.ForeignKeyConstraint(['user_game_id'], ['user_games.id'], name=op.f('fk_play_setups_user_game_id_user_games'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_play_setups'))
    )


def downgrade() -> None:
    op.drop_table('play_setups')
    op.drop_table('log_entries')
    op.drop_table('user_games')
    op.drop_table('game_genres')
    op.drop_index(op.f('ix_games_title'), table_name='games')
    op.drop_table('games')
    op.drop_table('devices')
    op.drop_index('uq_users_username_lower', table_name='users')
    op.drop_index('uq_users_email_lower', table_name='users')
    op.drop_table('users')
    op.drop_table('platforms')
    op.drop_table('genres')
    op.drop_table('emulators')
    op.drop_table('device_models')
    # Alembic no elimina los tipos enum al borrar las tablas.
    op.execute("DROP TYPE performance")
    op.execute("DROP TYPE log_kind")
    op.execute("DROP TYPE game_status")
