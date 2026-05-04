from __future__ import annotations

import html as _html
from datetime import date
from typing import Any


def build_pipeline_email(data: dict[str, Any]) -> str:
    files = data.get("files") or []

    def esc(value: Any) -> str:
        return _html.escape("" if value is None else str(value))

    title_text = "Pipeline Completed" if data["failure_count"] == 0 else "Pipeline Completed with Errors"

    html = f"""
<html>
<body style="font-family: Arial, sans-serif; background:#f5f5f5; padding:20px;">

  <div style="max-width:600px;margin:auto;background:white;padding:20px;border-radius:8px;">

    <h2>
      {esc(title_text)}
    </h2>

    <p style="color:#555;font-size:14px;">
      Run ID: {esc(data.get('run_id'))}<br/>
      Duration: {esc(data.get('duration'))}
    </p>

    <hr/>

    <h3>Summary</h3>
    <p>Total Files: {esc(data.get('total_files'))}</p>
    <p style="color:green;">Successful: {esc(data.get('success_count'))}</p>
    <p style="color:red;">Failed: {esc(data.get('failure_count'))}</p>

    <hr/>

    <h3>Files</h3>

    <table style="width:100%;border-collapse:collapse;">
      <tr style="background:#f0f0f0;">
        <th style="padding:8px;text-align:left;">File</th>
        <th style="padding:8px;">Status</th>
        <th style="padding:8px;">Details</th>
      </tr>

      {''.join([
        f'''
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee;vertical-align:top;line-height:1.4;">
            {esc(f.get('name'))}
          </td>
          <td style="padding:8px;text-align:center;color:{'green' if f.get('status')=='COMPLETED' else 'red'};border-bottom:1px solid #eee;vertical-align:top;line-height:1.4;white-space:nowrap;">
            {'Completed' if f.get('status')=='COMPLETED' else 'Failed'}
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;vertical-align:top;line-height:1.4;">
            {esc(f.get('error',''))}
          </td>
        </tr>
        '''
        for f in files
      ])}

    </table>

    <hr/>

    <h3>Accessibility Results</h3>
    <p>✅ Passed: {esc(data.get('passed'))}</p>
    <p>❌ Failed: {esc(data.get('failed'))}</p>
    <p>⚠ Needs Manual Check: {esc(data.get('manual'))}</p>

    <div style="text-align:center;margin-top:20px;">
      <a href="{esc(data.get('dashboard_url'))}" 
         style="background:#2563eb;color:white;padding:10px 16px;border-radius:6px;text-decoration:none;">
        View Dashboard
      </a>
    </div>

  </div>

</body>
</html>
"""

    return html


def build_eod_summary_email(data: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return _html.escape("" if value is None else str(value))

    report_date: date = data.get("date")
    runs = data.get("runs") or []
    totals = data.get("totals") or {}

    rows = "".join(
        [
            f"""
            <tr>
              <td style="padding:8px;border-bottom:1px solid #eee;">{index + 1}</td>
              <td style="padding:8px;border-bottom:1px solid #eee;">{esc(run.get('run_id'))}</td>
              <td style="padding:8px;border-bottom:1px solid #eee;">{esc(run.get('total_files'))}</td>
              <td style="padding:8px;border-bottom:1px solid #eee;color:green;">{esc(run.get('success_count'))}</td>
              <td style="padding:8px;border-bottom:1px solid #eee;color:red;">{esc(run.get('failure_count'))}</td>
              <td style="padding:8px;border-bottom:1px solid #eee;">{esc(run.get('status'))}</td>
            </tr>
            """
            for index, run in enumerate(runs)
        ]
    )

    if not rows:
        rows = """
        <tr>
          <td colspan="6" style="padding:8px;border-bottom:1px solid #eee;color:#666;">No runs today.</td>
        </tr>
        """

    return f"""
<html>
<body style="font-family: Arial, sans-serif; background:#f5f5f5; padding:20px;">
  <div style="max-width:700px;margin:auto;background:white;padding:20px;border-radius:8px;">
    <h2>Daily Pipeline Summary</h2>
    <p style="color:#555;font-size:14px;">Date: {esc(report_date.isoformat() if report_date else '')}</p>
    <hr/>
    <h3>Overall</h3>
    <p>Total Runs: {esc(totals.get('runs', 0))}</p>
    <p style="color:green;">Successful Runs: {esc(totals.get('success_runs', 0))}</p>
    <p style="color:red;">Failed Runs: {esc(totals.get('failed_runs', 0))}</p>
    <p>Total Files: {esc(totals.get('files', 0))}</p>
    <p style="color:green;">Successful Files: {esc(totals.get('success_files', 0))}</p>
    <p style="color:red;">Failed Files: {esc(totals.get('failed_files', 0))}</p>
    <hr/>
    <h3>Run-wise Summary</h3>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="background:#f0f0f0;">
        <th style="padding:8px;text-align:left;">#</th>
        <th style="padding:8px;text-align:left;">Run ID</th>
        <th style="padding:8px;text-align:left;">Files</th>
        <th style="padding:8px;text-align:left;">Success</th>
        <th style="padding:8px;text-align:left;">Failed</th>
        <th style="padding:8px;text-align:left;">Status</th>
      </tr>
      {rows}
    </table>
  </div>
</body>
</html>
"""
