from app.classification import heuristic_classify


def test_payroll_is_restricted_financial_data():
    result = heuristic_classify("employee_payroll.xlsx", "HR/Payroll/employee_payroll.xlsx")
    assert result.sensitivity == "Restricted"
    assert "Financial" in result.labels
    assert result.business_domain == "HR"


def test_terraform_is_confidential_source_code():
    result = heuristic_classify("main.tf", "infrastructure/aws/main.tf")
    assert result.sensitivity == "Confidential"
    assert "Source Code" in result.labels
