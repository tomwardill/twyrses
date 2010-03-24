# Create your views here.

from django.shortcuts import render_to_response
from django.template import RequestContext


def home(request):
    
    
    return render_to_response('home.html', {}, context_instance = RequestContext(request))

def license(request):
    
    
    return render_to_response('license.html', {}, context_instance = RequestContext(request))

def contributors(request):
    
    
    return render_to_response('contributors.html', {}, context_instance = RequestContext(request))