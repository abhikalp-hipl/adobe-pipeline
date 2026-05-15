import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class DocumentStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    TAGGED = "TAGGED"
    CHECKED = "CHECKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PipelineRunStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Designated department admin (Microsoft / notifications); must be one of distribution emails when set.
    admin_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    config: Mapped["DepartmentConfig | None"] = relationship(
        back_populates="department",
        uselist=False,
        cascade="all, delete-orphan",
    )
    credentials: Mapped["DepartmentCredentials | None"] = relationship(
        back_populates="department",
        uselist=False,
        cascade="all, delete-orphan",
    )
    oauth_token: Mapped["DepartmentOAuthToken | None"] = relationship(
        back_populates="department",
        uselist=False,
        cascade="all, delete-orphan",
    )
    email_members: Mapped[list["DepartmentEmailMember"]] = relationship(
        back_populates="department",
        cascade="all, delete-orphan",
    )


class DepartmentConfig(Base):
    __tablename__ = "department_configs"
    __table_args__ = (UniqueConstraint("department_id", name="uq_department_config_dept"),)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    department_id: Mapped[str] = mapped_column(String(36), ForeignKey("departments.id"), nullable=False)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule_time: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00")
    intake_folder: Mapped[str] = mapped_column(String(512), nullable=False, default="AdobePipeline/intake")
    processed_folder: Mapped[str] = mapped_column(String(512), nullable=False, default="AdobePipeline/processed")
    output_success_folder: Mapped[str] = mapped_column(
        String(512), nullable=False, default="AdobePipeline/output/success"
    )
    output_failure_folder: Mapped[str] = mapped_column(
        String(512), nullable=False, default="AdobePipeline/output/failure"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    department: Mapped["Department"] = relationship(back_populates="config")


class DepartmentCredentials(Base):
    __tablename__ = "department_credentials"
    __table_args__ = (UniqueConstraint("department_id", name="uq_department_credentials_dept"),)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    department_id: Mapped[str] = mapped_column(String(36), ForeignKey("departments.id"), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)

    department: Mapped["Department"] = relationship(back_populates="credentials")


class DepartmentOAuthToken(Base):
    __tablename__ = "department_oauth_tokens"
    __table_args__ = (UniqueConstraint("department_id", name="uq_department_oauth_dept"),)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    department_id: Mapped[str] = mapped_column(String(36), ForeignKey("departments.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="microsoft")
    connected_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    access_token: Mapped[str] = mapped_column(String, nullable=False)
    refresh_token: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    department: Mapped["Department"] = relationship(back_populates="oauth_token")


class DepartmentEmailMember(Base):
    __tablename__ = "department_email_members"
    __table_args__ = (UniqueConstraint("department_id", "email", name="uq_department_email_member"),)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    department_id: Mapped[str] = mapped_column(String(36), ForeignKey("departments.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    department: Mapped["Department"] = relationship(back_populates="email_members")


class SuperAdmin(Base):
    __tablename__ = "super_admins"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    username: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    department_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("departments.id"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class UserToken(Base):
    __tablename__ = "user_tokens"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="microsoft")
    user_email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    access_token: Mapped[str] = mapped_column(String, nullable=False)
    refresh_token: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class EmailGroup(Base):
    __tablename__ = "email_group"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    department_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("departments.id"), nullable=True, index=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration: Mapped[str] = mapped_column(String(64), nullable=False, default="0s")
    total_files: Mapped[int] = mapped_column(nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[PipelineRunStatus] = mapped_column(
        Enum(PipelineRunStatus),
        nullable=False,
        default=PipelineRunStatus.COMPLETED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    files: Mapped[list["PipelineRunFile"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class PipelineRunFile(Base):
    __tablename__ = "pipeline_run_files"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    # Prefix used for pipeline outputs (matches *_accessibility_report.json on disk / OneDrive).
    output_stem: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[PipelineRunStatus] = mapped_column(Enum(PipelineRunStatus), nullable=False)
    error_message: Mapped[str] = mapped_column(String, nullable=False, default="")
    accessibility_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accessibility_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accessibility_manual: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    run: Mapped[PipelineRun] = relationship(back_populates="files")


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    department_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("departments.id"), nullable=True, index=True)
    eod_time: Mapped[str] = mapped_column(String(5), nullable=False, default="18:00")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scheduler_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    last_sent_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
