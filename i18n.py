"""Shared locale data for the public-facing reports.

The decoder and its clinical-safety boundaries are locale-independent. This
module only contains human-facing labels and explanatory copy so JSON,
Markdown, HTML, PDF and the browser can use the same locale names.
"""

SUPPORTED_LOCALES = ('zh-CN', 'en-US')


def normalize_locale(value):
    """Return one of the supported locale identifiers."""
    value = str(value or '').replace('_', '-').lower()
    return 'en-US' if value == 'en' or value.startswith('en-') else 'zh-CN'


CONTEXT_FIELDS_EN = {
    'unrefreshed': 'Often still unrefreshed after waking',
    'sleepiness': 'Daytime sleepiness is persistent or worsening',
    'mask_problem': 'Mask leak, noise or dryness affects use',
    'mask_off': 'The mask is removed during sleep or not put back on',
    'gasping': 'Repeated gasping or witnessed pauses despite using the device',
    'drowsy_driving': 'Too drowsy to drive or operate equipment safely',
}


GLOSSARY_EN = {
    'ahi': ('AHI · apnea-hypopnea index', "The number of apneas and hypopneas per hour of sleep. It is one important measure in sleep-apnea assessment, but should be considered with oxygen and symptoms. This software cannot confirm the manufacturer's AHI from this card."),
    'frequency': ('Respiratory event index · estimated', "Total device entries for apneas and hypopneas divided by total treatment hours. It can show a treatment direction, but entries may be grouped by minute and have not been matched item by item to the manufacturer's AHI. This software does not grade severity."),
    'assessment': ('Provisional assessment and confidence', 'A directional assessment combines event level, period-to-period trend, treatment time and the reported experience. Confidence describes how complete the evidence is; it is not a probability of illness. When symptoms are unanswered, only the device-indicated direction is assessed.'),
    'usage': ('Average treatment time', 'The average time the device was used on days with a settled record. The device may also be worn while awake, so this is not the same as sleep time. Missing dates are not counted as zero use.'),
    'comparison': ('Previous period and same period last year', 'The previous period is the adjacent period with the same number of calendar days. The year-over-year period is aligned by month and day. Both use total entries divided by total treatment hours. At least 7 settled days and 70% coverage in each period are required; this is a data rule, not a disease threshold.'),
    'OSA': ('OSA · obstructive apnea', 'The upper airway narrows or closes and airflow stops. Here it means an entry labelled this way by the device; the manufacturer definition still needs checking.'),
    'CSA': ('CSA · central apnea', 'Breathing drive temporarily decreases and respiratory effort stops. A device label is not a diagnosis of central sleep apnea and should not be used to change pressure without a clinician.'),
    'HYP': ('HYP · hypopnea', 'Airflow is reduced without necessarily stopping completely. Formal sleep testing also considers oxygen reduction or arousal; here it is a device entry.'),
    'leak': ('Leak', 'Air leaking from the mask or mouth can affect comfort and treatment. It is not yet confirmed whether this card channel includes normal mask venting, so thresholds from another brand should not be applied.'),
    'pressure': ('Pressure · cmH₂O', 'The pressure used by the device to help keep the airway open, measured in centimetres of water. A higher or lower value does not by itself show whether sleep was good; settings require the prescribed clinical context.'),
    'p95': ('P95 · 95th percentile', '95% of retained samples are at or below this value. It is not the maximum or a target pressure. A few waveform dates cannot represent a whole month.'),
    'quality': ('Which data can speak to sleep', 'This card can record device use and respiratory entries. Actual sleep time, deep/REM sleep, arousals and overnight oxygen are not measured here. Combine it with your experience and, when needed, clinician-arranged sleep testing.'),
}


ASSESSMENT_RULES_EN = [
    'Event attention line: an estimated entry frequency of at least 5/h, or at least 3 dates reaching 5/h and representing 20% of settled days, prompts a check of residual events. 5/h is only a software review prompt informed by a commonly used residual-AHI range; this device metric is not calibrated to the manufacturer and is not a diagnostic boundary.',
    'Material change: the two periods must be eligible, with an absolute frequency change of at least 0.5/h and a relative change of at least 20%. Other non-zero changes are described as small. These are software rules to avoid over-reading fluctuation, not validated clinical significance thresholds.',
    'Treatment-coverage attention: at least 3 dates and 30% of settled days under 4 hours, an average treatment time at least 1 hour shorter than self-reported sleep, or a decrease of at least 1 hour and 20% from the previous period prompts a check that all sleep was covered. Four hours is not treated as sufficient therapy.',
    'Check symptoms and barriers to use first, then combine events and trend. Fewer than 7 settled days or under 70% coverage lowers trend confidence. Symptoms or clear event signals can still prompt action before the record is complete. The highest overall confidence is marked moderate while manufacturer and clinical comparisons remain outstanding.',
]


SOURCES_EN = [
    {'id': 'NIH-LIVING', 'title': 'NIH · Living with sleep apnea and drowsy driving', 'url': 'https://www.nhlbi.nih.gov/health/sleep-apnea/living-with'},
    {'id': 'NIH-AHI', 'title': 'MedlinePlus · Sleep studies and the meaning of AHI', 'url': 'https://medlineplus.gov/ency/article/003932.htm'},
    {'id': 'AASM2021', 'title': 'AASM 2021 · Long-term OSA management and repeat testing', 'url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC8314660/'},
    {'id': 'ATS2013', 'title': 'ATS 2013 · PAP adherence records, residual events and leak', 'url': 'https://www.thoracic.org/statements/resources/sleep-medicine/CPAP-Adherence-Tracking-Systems.pdf'},
    {'id': 'ATS-PAP', 'title': 'ATS · PAP treatment and use during all sleep periods', 'url': 'https://site.thoracic.org/advocacy-patients/patient-resources/positive-airway-pressure-cpap-and-bpap-for-adults-with-obstructive-sleep-apnea'},
    {'id': 'ATS-MASK', 'title': 'ATS · Troubleshooting PAP mask and use problems', 'url': 'https://site.thoracic.org/advocacy-patients/patient-resources/pap-therapy-quick-tips-for-troubleshooting-to-address-problems-with-use'},
]


QUESTIONS_EN = [
    "Does the manufacturer report's AHI and event classification agree with the USR entry frequency shown here?",
    'Was the device worn throughout actual sleep, including naps? Could short use or gaps be explained by schedule, mask removal or missing data?',
    'Did mask fit, tubing, dryness or noise affect use? How does the manufacturer define its leak value?',
    'If sleepiness or other symptoms continue, should there be further assessment or repeat sleep testing arranged by a clinician?',
]


COMPARISON_RULE_EN = 'Automatic comparison text is generated only when each period has at least 7 settled days and at least 70% coverage. This is a data-sufficiency rule, not a medical threshold.'
