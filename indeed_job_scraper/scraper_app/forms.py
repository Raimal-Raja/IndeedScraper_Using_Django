from django import forms
from django.conf import settings

class JobSearchForm(forms.Form):
    keyword = forms.CharField(
        max_length=100,
        label='Job Keyword',
        widget=forms.TextInput(attrs={'placeholder': 'e.g., Python Developer'})
    )
    country = forms.ChoiceField(
        choices=[(k, k) for k in settings.JOB_DOMAINS.keys()],
        label='Country'
    )
    browser_backend = forms.ChoiceField(
        choices=[('selenium', 'Standard Chrome'), ('undetected', 'Undetected Chrome (experimental)')],
        required=False, initial='selenium', label='Browser mode')
    pacing = forms.ChoiceField(
        choices=[('slow', 'Slow (5-7 seconds)'), ('normal', 'Normal (2-4 seconds)')],
        required=False, initial='slow', label='Request pacing')

    manual_verification = forms.BooleanField(required=False, initial=True, label='Pause for manual login or verification')
