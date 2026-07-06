-- Client Analytics Survey ETL Pipeline schema (SQL Server / SSMS variant)
-- T-SQL equivalent of schema.sql. See schema.md for a human-readable
-- description. Assumes the target database already exists/was just
-- created (see db/setup_db.py::_get_sqlserver_connection).

IF OBJECT_ID(N'dbo.surveys', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.surveys (
        survey_id           NVARCHAR(50)   NOT NULL PRIMARY KEY,
        client_or_form_id   NVARCHAR(50)   NULL,
        survey_title        NVARCHAR(500)  NULL,
        location_store_id   NVARCHAR(50)   NULL,
        location_name       NVARCHAR(200)  NULL,
        submitted_at        NVARCHAR(50)   NULL,
        score                FLOAT          NULL,
        responses_json       NVARCHAR(MAX)  NULL,
        loaded_at            NVARCHAR(50)   NOT NULL,
        opened                BIT           NOT NULL DEFAULT 0,
        opened_at             NVARCHAR(50)  NULL,
        command_request_id    NVARCHAR(100) NULL,
        open_error             NVARCHAR(MAX) NULL,
        campaign               NVARCHAR(50)  NULL,
        survey_status           NVARCHAR(100) NULL,
        attachments_count        INT           NULL,
        fieldworker_login         NVARCHAR(100) NULL,
        fieldworker_name           NVARCHAR(200) NULL,
        workflow_step_id            INT           NULL
    );
END;

IF OBJECT_ID(N'dbo.etl_runs', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_runs (
        run_id                  INT IDENTITY(1,1) PRIMARY KEY,
        started_at              NVARCHAR(50) NOT NULL,
        finished_at             NVARCHAR(50) NULL,
        surveys_extracted       INT NOT NULL DEFAULT 0,
        surveys_loaded          INT NOT NULL DEFAULT 0,
        surveys_duplicate       INT NOT NULL DEFAULT 0,
        surveys_marked_opened   INT NOT NULL DEFAULT 0,
        error_count             INT NOT NULL DEFAULT 0,
        status                  NVARCHAR(20) NOT NULL DEFAULT 'running'
    );
END;
