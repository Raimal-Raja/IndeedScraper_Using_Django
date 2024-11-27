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