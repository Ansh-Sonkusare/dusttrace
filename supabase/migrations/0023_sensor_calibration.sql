-- Sensor Audit (issue #58): each site sensor's last calibration on record. BMC wants one every 2 months;
-- the audit fails a sensor whose date is older. For a simulated sensor the date is simulated too, like
-- everything else about it (`site_sensors.simulated`).

alter table site_sensors add column if not exists calibrated_on date;
