"""Esporta tutti i modelli per Alembic autogenerate e per le query."""

from .activity import ActivityLog
from .alerts import Alert, AlertMatch
from .articles import Article
from .base import Base, TimestampMixin
from .notifications import Notification
from .push import PushSubscription
from .knowledge import (
    ArticleEntity,
    ArticleTopic,
    Entity,
    EntitySourceCount,
    Topic,
    TopicCompositeRule,
    TopicTermRule,
)
from .sources import Category, FeaturedSource, Source, UserSource
from .users import (
    AuthSession,
    EmailVerificationToken,
    PasswordResetToken,
    ReservedUsername,
    User,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "AuthSession",
    "EmailVerificationToken",
    "PasswordResetToken",
    "ReservedUsername",
    "Source",
    "UserSource",
    "Category",
    "FeaturedSource",
    "Article",
    "Topic",
    "Entity",
    "ArticleTopic",
    "ArticleEntity",
    "EntitySourceCount",
    "TopicTermRule",
    "TopicCompositeRule",
    "ActivityLog",
    "Notification",
    "Alert",
    "AlertMatch",
    "PushSubscription",
]
